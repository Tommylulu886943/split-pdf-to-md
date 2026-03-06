from __future__ import annotations

import logging
import os
from typing import Callable

from pypdf import PdfReader, PdfWriter

from .range_extractor import PageRange
from .utils import sanitize_filename

logger = logging.getLogger("split-pdf")


def split_pdf(
    pdf_path: str,
    ranges: list[PageRange],
    output_dir: str,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[str]:
    """
    Split a PDF into multiple files based on page ranges.

    Args:
        pdf_path: Source PDF path.
        ranges: List of PageRange objects.
        output_dir: Directory to write split PDFs.
        on_progress: Optional callback(current, total, filename).

    Returns:
        List of output PDF file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    output_paths = []

    for i, rg in enumerate(ranges, 1):
        if rg.end_page > total_pages:
            raise ValueError(
                f"Range '{rg.name}' end_page({rg.end_page}) exceeds total pages({total_pages})"
            )

        safe_name = sanitize_filename(rg.name)
        filename = f"{i:02d}_{safe_name}.pdf"
        output_path = os.path.join(output_dir, filename)

        writer = PdfWriter()
        # pypdf uses 0-based indexing
        for page_idx in range(rg.start_page - 1, rg.end_page):
            writer.add_page(reader.pages[page_idx])

        with open(output_path, "wb") as f:
            writer.write(f)

        # Verify
        actual_pages = rg.page_count()
        written_reader = PdfReader(output_path)
        written_pages = len(written_reader.pages)
        if written_pages != actual_pages:
            logger.warning(
                f"{filename}: expected {actual_pages} pages, got {written_pages}"
            )

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"{filename}: {written_pages} pages, {size_mb:.1f} MB")

        output_paths.append(output_path)

        if on_progress:
            on_progress(i, len(ranges), filename)

    return output_paths
