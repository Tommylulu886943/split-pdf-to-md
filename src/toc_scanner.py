from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

logger = logging.getLogger("split-pdf")

TOC_PATTERNS = [
    re.compile(r"(?:chapter|section|part)\s*\d+", re.IGNORECASE),
    re.compile(r"^第[一二三四五六七八九十百千\d]+[章節篇部]", re.MULTILINE),
    re.compile(r".{5,60}\s*\.{3,}\s*\d+"),  # "Title ...... 42"
    re.compile(r"^\d+\.\d+\s+\S+", re.MULTILINE),  # "1.1 Introduction"
]


@dataclass
class BookmarkEntry:
    title: str
    page: int
    level: int


@dataclass
class TOCInfo:
    total_pages: int
    bookmarks: list[BookmarkEntry] = field(default_factory=list)
    toc_text: str = ""
    sample_pages: dict[int, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)

    def to_prompt_context(self) -> str:
        """Format TOC info as context for LLM prompt."""
        parts = [f"Total pages: {self.total_pages}"]

        if self.metadata:
            meta_str = ", ".join(f"{k}: {v}" for k, v in self.metadata.items() if v)
            if meta_str:
                parts.append(f"Metadata: {meta_str}")

        if self.bookmarks:
            bm_lines = []
            for bm in self.bookmarks[:50]:  # cap at 50 to save tokens
                indent = "  " * bm.level
                bm_lines.append(f"{indent}- {bm.title} (p.{bm.page})")
            parts.append("Bookmarks:\n" + "\n".join(bm_lines))

        if self.toc_text:
            parts.append(f"TOC text:\n{self.toc_text[:2000]}")

        if self.sample_pages:
            samples = []
            for pg, text in sorted(self.sample_pages.items()):
                samples.append(f"Page {pg}: {text}")
            parts.append("Page samples:\n" + "\n".join(samples))

        return "\n\n".join(parts)


def scan_toc(pdf_path: str, scan_pages: int = 30) -> TOCInfo:
    """
    Multi-strategy scan of PDF structure.

    Strategy priority:
    1. PDF bookmarks (most accurate)
    2. TOC page detection (regex on first N pages)
    3. Page sampling (uniform samples for context)
    """
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    info = TOCInfo(total_pages=total_pages)

    # Metadata
    if reader.metadata:
        for key in ("title", "author", "subject"):
            val = getattr(reader.metadata, key, None)
            if val:
                info.metadata[key] = str(val)

    # Strategy 1: PDF bookmarks
    info.bookmarks = _extract_bookmarks(reader)
    if info.bookmarks:
        logger.info(f"Found {len(info.bookmarks)} bookmarks")

    # Strategy 2: TOC page detection
    scan_limit = min(scan_pages, total_pages)
    toc_fragments = []
    for i in range(scan_limit):
        text = _extract_page_text(reader, i)
        if not text:
            continue
        for pattern in TOC_PATTERNS:
            if pattern.search(text):
                toc_fragments.append(f"[Page {i + 1}]\n{text[:500]}")
                break

    if toc_fragments:
        info.toc_text = "\n---\n".join(toc_fragments[:10])  # cap at 10 pages
        logger.info(f"Found TOC-like content in {len(toc_fragments)} pages")

    # Strategy 3: Page sampling (if no bookmarks and limited TOC)
    if not info.bookmarks and len(toc_fragments) < 3:
        sample_indices = _uniform_sample_indices(total_pages, count=8)
        for idx in sample_indices:
            text = _extract_page_text(reader, idx)
            if text:
                info.sample_pages[idx + 1] = text[:200]
        logger.info(f"Sampled {len(info.sample_pages)} pages for context")

    return info


def _extract_bookmarks(reader: PdfReader) -> list[BookmarkEntry]:
    """Extract bookmarks/outline from PDF."""
    entries = []
    try:
        outline = reader.outline
        if outline:
            _walk_outline(reader, outline, entries, level=0)
    except Exception as e:
        logger.debug(f"Could not extract bookmarks: {e}")
    return entries


def _walk_outline(reader: PdfReader, outline, entries: list[BookmarkEntry], level: int):
    """Recursively walk PDF outline tree."""
    for item in outline:
        if isinstance(item, list):
            _walk_outline(reader, item, entries, level + 1)
        else:
            try:
                page_num = reader.get_destination_page_number(item)
                entries.append(BookmarkEntry(
                    title=item.title,
                    page=page_num + 1,  # 1-based
                    level=level,
                ))
            except Exception:
                pass


def _extract_page_text(reader: PdfReader, page_index: int) -> str:
    """Extract text from a page, returning empty string on failure."""
    try:
        return reader.pages[page_index].extract_text() or ""
    except Exception:
        return ""


def _uniform_sample_indices(total: int, count: int = 8) -> list[int]:
    """Return uniformly distributed page indices."""
    if total <= count:
        return list(range(total))
    step = total / (count + 1)
    return [int(step * (i + 1)) for i in range(count)]
