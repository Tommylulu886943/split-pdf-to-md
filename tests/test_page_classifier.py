"""Tests for page content classifier."""
import pytest

from src.page_classifier import (
    PageContentType,
    PageClassification,
    classify_pages,
    group_consecutive_pages,
)


@pytest.fixture
def prose_pdf(tmp_path):
    """Create a PDF with only text content."""
    import pymupdf
    path = str(tmp_path / "prose.pdf")
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Page {i + 1}. " + "This is paragraph text. " * 20, fontsize=11)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def table_pdf(tmp_path):
    """Create a PDF with a large table drawn using lines."""
    import pymupdf
    path = str(tmp_path / "table.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Draw a grid table covering most of the page
    x0, y0 = 50, 50
    cols = 5
    rows = 15
    col_w = 100
    row_h = 40

    # Draw horizontal lines
    for r in range(rows + 1):
        y = y0 + r * row_h
        page.draw_line((x0, y), (x0 + cols * col_w, y))

    # Draw vertical lines
    for c in range(cols + 1):
        x = x0 + c * col_w
        page.draw_line((x, y0), (x, y0 + rows * row_h))

    # Add text in cells
    for r in range(rows):
        for c in range(cols):
            x = x0 + c * col_w + 5
            y = y0 + r * row_h + 20
            if r == 0:
                page.insert_text((x, y), f"Col {c + 1}", fontsize=9)
            else:
                page.insert_text((x, y), f"R{r}C{c}", fontsize=9)

    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def mixed_pdf(tmp_path):
    """Create a PDF with text page followed by table page."""
    import pymupdf
    path = str(tmp_path / "mixed.pdf")
    doc = pymupdf.open()

    # Page 1: prose
    page1 = doc.new_page(width=612, height=792)
    page1.insert_text((72, 72), "This is a text-only page with paragraphs.\n" * 10, fontsize=11)

    # Page 2: table (draw grid)
    page2 = doc.new_page(width=612, height=792)
    x0, y0 = 50, 50
    cols, rows = 4, 20
    col_w, row_h = 120, 30
    for r in range(rows + 1):
        y = y0 + r * row_h
        page2.draw_line((x0, y), (x0 + cols * col_w, y))
    for c in range(cols + 1):
        x = x0 + c * col_w
        page2.draw_line((x, y0), (x, y0 + rows * row_h))
    for r in range(rows):
        for c in range(cols):
            page2.insert_text((x0 + c * col_w + 5, y0 + r * row_h + 18), f"V{r}{c}", fontsize=8)

    # Page 3: prose again
    page3 = doc.new_page(width=612, height=792)
    page3.insert_text((72, 72), "Another text page.\n" * 10, fontsize=11)

    doc.save(path)
    doc.close()
    return path


class TestClassifyPages:
    def test_prose_pages(self, prose_pdf):
        results = classify_pages(prose_pdf)
        assert len(results) == 3
        for r in results:
            assert r.content_type == PageContentType.PROSE

    def test_table_page(self, table_pdf):
        results = classify_pages(table_pdf)
        assert len(results) == 1
        # Should detect as table (dense or mixed)
        assert results[0].content_type in (
            PageContentType.TABLE_DENSE,
            PageContentType.TABLE_MIXED,
        )
        assert results[0].table_count >= 1

    def test_mixed_pdf(self, mixed_pdf):
        results = classify_pages(mixed_pdf)
        assert len(results) == 3
        # Page 1 should be prose
        assert results[0].content_type == PageContentType.PROSE
        # Page 2 should be table
        assert results[1].content_type in (
            PageContentType.TABLE_DENSE,
            PageContentType.TABLE_MIXED,
        )
        # Page 3 should be prose
        assert results[2].content_type == PageContentType.PROSE

    def test_classification_fields(self, table_pdf):
        results = classify_pages(table_pdf)
        r = results[0]
        assert r.page_index == 0
        assert r.table_area_ratio > 0
        assert r.text_length > 0


class TestGroupConsecutivePages:
    def test_empty(self):
        assert group_consecutive_pages([]) == []

    def test_single_type(self):
        cls = [
            PageClassification(0, PageContentType.PROSE),
            PageClassification(1, PageContentType.PROSE),
            PageClassification(2, PageContentType.PROSE),
        ]
        groups = group_consecutive_pages(cls)
        assert len(groups) == 1
        assert groups[0] == (PageContentType.PROSE, [0, 1, 2])

    def test_alternating_types(self):
        cls = [
            PageClassification(0, PageContentType.PROSE),
            PageClassification(1, PageContentType.TABLE_DENSE),
            PageClassification(2, PageContentType.PROSE),
        ]
        groups = group_consecutive_pages(cls)
        assert len(groups) == 3
        assert groups[0] == (PageContentType.PROSE, [0])
        assert groups[1] == (PageContentType.TABLE_DENSE, [1])
        assert groups[2] == (PageContentType.PROSE, [2])

    def test_consecutive_tables(self):
        cls = [
            PageClassification(0, PageContentType.TABLE_DENSE),
            PageClassification(1, PageContentType.TABLE_DENSE),
            PageClassification(2, PageContentType.PROSE),
        ]
        groups = group_consecutive_pages(cls)
        assert len(groups) == 2
        assert groups[0] == (PageContentType.TABLE_DENSE, [0, 1])
        assert groups[1] == (PageContentType.PROSE, [2])
