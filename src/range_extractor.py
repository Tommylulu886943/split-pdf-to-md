from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, asdict

import anthropic

from .toc_scanner import scan_toc, TOCInfo

logger = logging.getLogger("split-pdf")

# Matches patterns like: "100-500", "100~500", "100到500", "100至500"
# Optionally followed by a label
RANGE_PATTERN = re.compile(
    r"(\d+)\s*[-~到至]\s*(\d+)\s*[,，;；\s]*([^,，;；\d]*)"
)


@dataclass
class PageRange:
    name: str
    start_page: int  # 1-based, inclusive
    end_page: int  # 1-based, inclusive
    reason: str = ""

    def page_count(self) -> int:
        return self.end_page - self.start_page + 1


def extract_ranges(
    pdf_path: str,
    natural_desc: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 2000,
    toc_scan_pages: int = 30,
) -> list[PageRange]:
    """
    Parse natural language description into page ranges.

    Fast path: regex for explicit ranges like "100-500, 501-600".
    LLM path: Claude API with TOC context for semantic descriptions.
    """
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    # Fast path: try regex
    ranges = _try_fast_path(natural_desc, total_pages)
    if ranges:
        logger.info(f"Fast path: parsed {len(ranges)} ranges from description")
        return ranges

    # LLM path
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is required for semantic descriptions. "
            "Set it via environment variable or use explicit page ranges like '1-100, 101-200'."
        )

    logger.info("Scanning PDF structure for LLM context...")
    toc_info = scan_toc(pdf_path, scan_pages=toc_scan_pages)

    logger.info("Calling Claude API to parse page ranges...")
    ranges = _llm_extract(natural_desc, toc_info, api_key, model, max_tokens)

    # Validate
    ranges = _validate_ranges(ranges, total_pages)
    logger.info(f"LLM path: extracted {len(ranges)} ranges")
    return ranges


def _try_fast_path(desc: str, total_pages: int) -> list[PageRange] | None:
    """Try to parse explicit page ranges via regex. Returns None if not purely explicit."""
    matches = RANGE_PATTERN.findall(desc)
    if not matches:
        return None

    ranges = []
    for i, (start_s, end_s, label) in enumerate(matches, 1):
        start, end = int(start_s), int(end_s)
        if start >= end or start < 1 or end > total_pages:
            return None  # Suspicious, fall through to LLM

        label = label.strip()
        name = label if label else f"part_{i}"
        ranges.append(PageRange(name=name, start_page=start, end_page=end, reason="regex"))

    # Check that we captured something meaningful
    if not ranges:
        return None

    # Verify no overlaps
    sorted_ranges = sorted(ranges, key=lambda r: r.start_page)
    for i in range(1, len(sorted_ranges)):
        if sorted_ranges[i].start_page <= sorted_ranges[i - 1].end_page:
            return None  # Overlapping, let LLM handle

    return ranges


def _llm_extract(
    desc: str,
    toc_info: TOCInfo,
    api_key: str,
    model: str,
    max_tokens: int,
) -> list[PageRange]:
    """Call Claude API to extract page ranges."""
    context = toc_info.to_prompt_context()

    system_prompt = (
        "You are a PDF structure analysis expert. "
        "Output ONLY a JSON array, no other text, no markdown fences."
    )

    user_prompt = f"""## PDF Info
{context}

## User Request
{desc}

## Output Format
JSON array where each element has:
- name: string, short name for the section (safe for filenames, no special chars)
- start_page: integer, 1-based start page
- end_page: integer, 1-based end page (inclusive)
- reason: string, brief explanation (under 30 chars)

## Constraints
- start_page >= 1
- end_page <= {toc_info.total_pages}
- start_page < end_page
- Ranges must not overlap"""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text
    logger.debug(f"LLM response: {raw_text[:500]}")

    parsed = _parse_json_response(raw_text)
    return [
        PageRange(
            name=item.get("name", f"part_{i}"),
            start_page=item["start_page"],
            end_page=item["end_page"],
            reason=item.get("reason", "llm"),
        )
        for i, item in enumerate(parsed, 1)
    ]


def _parse_json_response(text: str) -> list[dict]:
    """
    Parse LLM JSON response with 3-layer fallback:
    1. Direct json.loads
    2. Extract ```json ... ``` block
    3. Extract first [ ... ] block
    """
    # Layer 1
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Layer 2: code fence
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Layer 3: first array
    array_match = re.search(r"\[.*\]", text, re.DOTALL)
    if array_match:
        try:
            result = json.loads(array_match.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}...")


def _validate_ranges(ranges: list[PageRange], total_pages: int) -> list[PageRange]:
    """Validate and fix ranges. Raises ValueError on unfixable issues."""
    if not ranges:
        raise ValueError("No page ranges extracted")

    validated = []
    for r in ranges:
        if r.start_page < 1:
            r.start_page = 1
        if r.end_page > total_pages:
            r.end_page = total_pages
        if r.start_page >= r.end_page:
            raise ValueError(
                f"Invalid range '{r.name}': start({r.start_page}) >= end({r.end_page})"
            )
        # Sanitize name
        r.name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", r.name)
        r.name = re.sub(r"\s+", "_", r.name.strip()) or f"part_{len(validated) + 1}"
        validated.append(r)

    # Check overlaps
    sorted_ranges = sorted(validated, key=lambda r: r.start_page)
    for i in range(1, len(sorted_ranges)):
        prev, curr = sorted_ranges[i - 1], sorted_ranges[i]
        if curr.start_page <= prev.end_page:
            raise ValueError(
                f"Overlapping ranges: '{prev.name}'({prev.start_page}-{prev.end_page}) "
                f"and '{curr.name}'({curr.start_page}-{curr.end_page})"
            )

    return validated


def save_ranges(ranges: list[PageRange], path: str):
    """Save ranges to JSON file."""
    data = [asdict(r) for r in ranges]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved ranges to {path}")


def load_ranges(path: str) -> list[PageRange]:
    """Load ranges from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [PageRange(**item) for item in data]
