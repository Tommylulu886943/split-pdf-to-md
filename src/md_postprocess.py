"""Markdown post-processor for token optimization."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class PostprocessConfig:
    remove_headers_footers: bool = True
    remove_page_numbers: bool = True
    normalize_whitespace: bool = True
    fix_broken_lines: bool = True


def postprocess_md(content: str, config: PostprocessConfig | None = None) -> str:
    """
    Post-process Markdown to reduce token usage and improve LLM readability.

    Steps (each toggleable via config):
    1. Remove repeated headers/footers
    2. Remove page number markers
    3. Normalize whitespace (collapse blank lines, trim trailing spaces)
    4. Fix broken lines (rejoin mid-sentence hard breaks)
    """
    if config is None:
        config = PostprocessConfig()

    if config.remove_headers_footers:
        content = _remove_repeated_headers_footers(content)

    if config.remove_page_numbers:
        content = _remove_page_numbers(content)

    if config.fix_broken_lines:
        content = _fix_broken_lines(content)

    if config.normalize_whitespace:
        content = _normalize_whitespace(content)

    return content


def _remove_repeated_headers_footers(content: str) -> str:
    """
    Detect and remove text that repeats across page boundaries.

    Algorithm:
    1. Split by page separators (--- or form feed)
    2. Collect first/last lines of each segment
    3. Lines appearing in >50% of segments are headers/footers -> remove
    """
    # Split by common page separators
    separators = re.compile(r"\n-{3,}\n|\f")
    segments = separators.split(content)

    if len(segments) < 4:
        return content

    # Collect candidate header/footer lines
    first_lines = []
    last_lines = []
    for seg in segments:
        lines = [l.strip() for l in seg.strip().splitlines() if l.strip()]
        if len(lines) >= 2:
            first_lines.append(lines[0])
            last_lines.append(lines[-1])

    threshold = len(segments) * 0.5
    remove_lines = set()

    for line, count in Counter(first_lines).items():
        if count >= threshold and len(line) > 3:
            remove_lines.add(line)

    for line, count in Counter(last_lines).items():
        if count >= threshold and len(line) > 3:
            remove_lines.add(line)

    if not remove_lines:
        return content

    # Remove matched lines
    result_lines = []
    for line in content.splitlines():
        if line.strip() not in remove_lines:
            result_lines.append(line)

    return "\n".join(result_lines)


def _remove_page_numbers(content: str) -> str:
    """Remove standalone page number lines."""
    # Patterns: "- 42 -", "Page 42", "42", "-- 42 --", "p. 42"
    page_num_pattern = re.compile(
        r"^[\s]*(?:"
        r"-{1,3}\s*\d+\s*-{1,3}"       # - 42 - or -- 42 --
        r"|[Pp](?:age|\.)\s*\d+"         # Page 42 or p. 42
        r"|\d{1,5}"                       # standalone number
        r")[\s]*$"
    )

    lines = content.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        # Only remove if the line is JUST a page number (short line)
        if stripped and len(stripped) <= 12 and page_num_pattern.match(stripped):
            continue
        result.append(line)

    return "\n".join(result)


def _fix_broken_lines(content: str) -> str:
    """
    Rejoin lines that were broken mid-sentence by PDF extraction.

    Heuristic: if a line does NOT end with sentence-ending punctuation
    and the next line starts with a lowercase letter, join them.
    Preserves markdown structure (headings, lists, blank lines, tables).
    """
    lines = content.splitlines()
    if not lines:
        return content

    result = [lines[0]]

    for i in range(1, len(lines)):
        prev = result[-1]
        curr = lines[i]

        if _should_join(prev, curr):
            result[-1] = prev.rstrip() + " " + curr.lstrip()
        else:
            result.append(curr)

    return "\n".join(result)


def _should_join(prev: str, curr: str) -> bool:
    """Determine if two lines should be joined."""
    prev_stripped = prev.rstrip()
    curr_stripped = curr.lstrip()

    # Don't join if either is empty
    if not prev_stripped or not curr_stripped:
        return False

    # Don't join markdown structural elements
    if curr_stripped.startswith(("#", "-", "*", "+", ">", "|", "```", "    ")):
        return False
    if prev_stripped.startswith(("#", "|", "```")):
        return False

    # Don't join if prev is a list item
    if re.match(r"^[\s]*[-*+]\s", prev) or re.match(r"^[\s]*\d+\.\s", prev):
        return False

    # Join if prev doesn't end with sentence-ending punct and curr starts lowercase
    sentence_enders = ".!?:;。！？：；」）】"
    if prev_stripped[-1] in sentence_enders:
        return False

    # curr must start with lowercase or continuation char
    if curr_stripped[0].islower() or curr_stripped[0] in "([\"'":
        return True

    return False


def _normalize_whitespace(content: str) -> str:
    """Collapse multiple blank lines to one, trim trailing whitespace."""
    # Trim trailing whitespace per line
    lines = [line.rstrip() for line in content.splitlines()]
    content = "\n".join(lines)

    # Collapse 3+ newlines to 2 (one blank line)
    content = re.sub(r"\n{3,}", "\n\n", content)

    # Trim leading/trailing
    return content.strip() + "\n"
