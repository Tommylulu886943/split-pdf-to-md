"""Page content classifier for content-aware PDF conversion."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("split-pdf")


class PageContentType(Enum):
    PROSE = "prose"
    TABLE_DENSE = "table_dense"    # >60% page area is tables
    TABLE_MIXED = "table_mixed"    # 15-60% page area is tables
    IMAGE_HEAVY = "image_heavy"    # >50% page area is images, minimal text


@dataclass
class PageClassification:
    page_index: int
    content_type: PageContentType
    table_count: int = 0
    table_area_ratio: float = 0.0
    image_area_ratio: float = 0.0
    text_length: int = 0


def classify_pages(pdf_path: str) -> list[PageClassification]:
    """Classify each page of a PDF by content type.

    Uses pymupdf's built-in table detection and image extraction
    to determine the dominant content type per page.
    """
    import pymupdf

    doc = pymupdf.open(pdf_path)
    results = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_area = page.rect.width * page.rect.height
        if page_area == 0:
            results.append(PageClassification(
                page_index=page_idx,
                content_type=PageContentType.PROSE,
            ))
            continue

        # Table detection
        table_area, table_count = _detect_tables(page, page_area)
        table_ratio = table_area / page_area

        # Image detection
        image_ratio = _detect_images(page, page_area)

        # Text length
        text_len = len(page.get_text().strip())

        # Classification logic
        content_type = _classify(table_ratio, table_count, image_ratio, text_len)

        results.append(PageClassification(
            page_index=page_idx,
            content_type=content_type,
            table_count=table_count,
            table_area_ratio=round(table_ratio, 3),
            image_area_ratio=round(image_ratio, 3),
            text_length=text_len,
        ))

    doc.close()

    # Log summary
    type_counts = {}
    for r in results:
        type_counts[r.content_type.value] = type_counts.get(r.content_type.value, 0) + 1
    logger.info(f"Page classification: {type_counts}")

    return results


def _detect_tables(page, page_area: float) -> tuple[float, int]:
    """Detect tables on a page. Returns (total_table_area, table_count)."""
    try:
        tables = page.find_tables()
        if not tables.tables:
            return 0.0, 0

        total_area = 0.0
        for table in tables.tables:
            bbox = table.bbox  # (x0, y0, x1, y1)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            total_area += w * h

        return total_area, len(tables.tables)
    except Exception as e:
        logger.debug(f"Table detection failed on page: {e}")
        return 0.0, 0


def _detect_images(page, page_area: float) -> float:
    """Detect image area ratio on a page."""
    try:
        images = page.get_images(full=True)
        if not images:
            return 0.0

        total_area = 0.0
        for img in images:
            # Try to get image bounding box from the page
            xref = img[0]
            img_rects = page.get_image_rects(xref)
            for rect in img_rects:
                total_area += rect.width * rect.height

        return min(total_area / page_area, 1.0)
    except Exception as e:
        logger.debug(f"Image detection failed on page: {e}")
        return 0.0


def _classify(
    table_ratio: float,
    table_count: int,
    image_ratio: float,
    text_len: int,
) -> PageContentType:
    """Determine content type from detected features."""
    # Dense table: >60% of page area is tables
    if table_ratio > 0.6:
        return PageContentType.TABLE_DENSE

    # Image heavy: >50% images and minimal text
    if image_ratio > 0.5 and text_len < 200:
        return PageContentType.IMAGE_HEAVY

    # Mixed table: 15-60% table area
    if table_ratio > 0.15 and table_count >= 1:
        return PageContentType.TABLE_MIXED

    return PageContentType.PROSE


def group_consecutive_pages(
    classifications: list[PageClassification],
) -> list[tuple[PageContentType, list[int]]]:
    """Group consecutive pages with the same content type.

    Returns list of (content_type, [page_indices]).
    """
    if not classifications:
        return []

    groups: list[tuple[PageContentType, list[int]]] = []
    current_type = classifications[0].content_type
    current_pages = [classifications[0].page_index]

    for cls in classifications[1:]:
        if cls.content_type == current_type:
            current_pages.append(cls.page_index)
        else:
            groups.append((current_type, current_pages))
            current_type = cls.content_type
            current_pages = [cls.page_index]

    groups.append((current_type, current_pages))
    return groups
