"""Multi-layer table extractor for PDF pages."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("split-pdf")


def extract_tables_from_page(page, page_index: int) -> str | None:
    """Extract tables from a single pymupdf page as Markdown.

    Layer 1: pymupdf built-in find_tables()
    Layer 2: pdfplumber fallback (if installed)

    Returns Markdown string or None if extraction failed.
    """
    # Layer 1: pymupdf
    md = _extract_pymupdf(page, page_index)
    if md:
        return md

    # Layer 2: pdfplumber
    md = _extract_pdfplumber(page, page_index)
    if md:
        return md

    logger.debug(f"Page {page_index + 1}: all table extraction layers failed")
    return None


def extract_tables_from_pages(
    pdf_path: str, page_indices: list[int]
) -> str:
    """Extract tables from multiple pages and combine as Markdown.

    Args:
        pdf_path: Path to PDF file.
        page_indices: List of 0-based page indices to extract.

    Returns:
        Combined Markdown string.
    """
    import pymupdf

    doc = pymupdf.open(pdf_path)
    parts = []

    for idx in page_indices:
        page = doc[idx]
        md = extract_tables_from_page(page, idx)
        if md:
            parts.append(md)
        else:
            # Fallback: plain text with layout preservation
            text = page.get_text("text").strip()
            if text:
                parts.append(text)
                logger.warning(
                    f"Page {idx + 1}: table extraction failed, using plain text"
                )

    doc.close()
    return "\n\n".join(parts) + "\n" if parts else "\n"


def _extract_pymupdf(page, page_index: int) -> str | None:
    """Extract tables using pymupdf's built-in table finder."""
    try:
        tables = page.find_tables()
        if not tables.tables:
            return None

        parts = []
        # Track which areas are covered by tables for non-table text
        table_bboxes = [t.bbox for t in tables.tables]

        # Get non-table text blocks
        text_blocks = _get_non_table_text(page, table_bboxes)

        # Combine tables and text blocks in reading order (by y-coordinate)
        elements: list[tuple[float, str]] = []

        for table in tables.tables:
            md_table = _pymupdf_table_to_md(table)
            if md_table:
                elements.append((table.bbox[1], md_table))  # y0 for ordering

        for y_pos, text in text_blocks:
            elements.append((y_pos, text))

        # Sort by vertical position
        elements.sort(key=lambda x: x[0])
        result = "\n\n".join(el[1] for el in elements)

        if result.strip():
            return result
        return None

    except Exception as e:
        logger.debug(f"Page {page_index + 1}: pymupdf table extraction error: {e}")
        return None


def _pymupdf_table_to_md(table) -> str | None:
    """Convert a pymupdf Table object to Markdown table format."""
    try:
        data = table.extract()
        if not data or not data[0]:
            return None

        # Clean cells: replace None with empty string, strip whitespace
        cleaned = []
        for row in data:
            cleaned.append([_clean_cell(cell) for cell in row])

        if not cleaned:
            return None

        col_count = max(len(row) for row in cleaned)

        # Pad rows to equal length
        for row in cleaned:
            while len(row) < col_count:
                row.append("")

        # Build markdown table
        lines = []
        # Header row
        lines.append("| " + " | ".join(cleaned[0]) + " |")
        # Separator
        lines.append("| " + " | ".join(["---"] * col_count) + " |")
        # Data rows
        for row in cleaned[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    except Exception as e:
        logger.debug(f"Table to markdown conversion error: {e}")
        return None


def _clean_cell(cell) -> str:
    """Clean a table cell value for Markdown."""
    if cell is None:
        return ""
    text = str(cell).strip()
    # Replace newlines within cells with space
    text = re.sub(r"\s*\n\s*", " ", text)
    # Escape pipe characters
    text = text.replace("|", "\\|")
    return text


def _get_non_table_text(
    page, table_bboxes: list[tuple]
) -> list[tuple[float, str]]:
    """Get text blocks that are NOT inside any table bounding box.

    Returns list of (y_position, text) tuples.
    """
    blocks = page.get_text("blocks")  # [(x0, y0, x1, y1, text, block_no, type)]
    result = []

    for block in blocks:
        if block[6] != 0:  # type 0 = text block
            continue

        bx0, by0, bx1, by1 = block[:4]
        text = block[4].strip()
        if not text:
            continue

        # Check if block overlaps significantly with any table
        in_table = False
        for tx0, ty0, tx1, ty1 in table_bboxes:
            # Calculate overlap
            ox0 = max(bx0, tx0)
            oy0 = max(by0, ty0)
            ox1 = min(bx1, tx1)
            oy1 = min(by1, ty1)

            if ox0 < ox1 and oy0 < oy1:
                overlap_area = (ox1 - ox0) * (oy1 - oy0)
                block_area = (bx1 - bx0) * (by1 - by0)
                if block_area > 0 and overlap_area / block_area > 0.5:
                    in_table = True
                    break

        if not in_table:
            result.append((by0, text))

    return result


def _extract_pdfplumber(page, page_index: int) -> str | None:
    """Extract tables using pdfplumber (fallback).

    Requires pdfplumber to be installed. Uses text-position-based
    column detection, which works better for borderless tables.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.debug("pdfplumber not installed, skipping fallback layer")
        return None

    try:
        # pdfplumber needs the PDF path and page number
        # Since we have a pymupdf page, we need to get the parent doc path
        doc = page.parent
        pdf_path = doc.name
        if not pdf_path:
            return None

        with pdfplumber.open(pdf_path) as pdf:
            if page_index >= len(pdf.pages):
                return None

            plumber_page = pdf.pages[page_index]
            tables = plumber_page.extract_tables()

            if not tables:
                return None

            parts = []
            for table_data in tables:
                if not table_data or not table_data[0]:
                    continue

                # Clean and build markdown
                cleaned = []
                for row in table_data:
                    cleaned.append([_clean_cell(cell) for cell in row])

                col_count = max(len(row) for row in cleaned)
                for row in cleaned:
                    while len(row) < col_count:
                        row.append("")

                lines = []
                lines.append("| " + " | ".join(cleaned[0]) + " |")
                lines.append("| " + " | ".join(["---"] * col_count) + " |")
                for row in cleaned[1:]:
                    lines.append("| " + " | ".join(row) + " |")
                parts.append("\n".join(lines))

            return "\n\n".join(parts) if parts else None

    except Exception as e:
        logger.debug(f"Page {page_index + 1}: pdfplumber extraction error: {e}")
        return None
