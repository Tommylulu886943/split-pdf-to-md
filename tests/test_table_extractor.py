"""Tests for table extractor."""
import pytest

from src.table_extractor import (
    extract_tables_from_pages,
    _clean_cell,
)


@pytest.fixture
def simple_table_pdf(tmp_path):
    """Create a PDF with a simple grid table."""
    import pymupdf
    path = str(tmp_path / "table.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Draw a 4x3 table
    x0, y0 = 72, 72
    cols, rows = 4, 3
    col_w, row_h = 120, 30

    for r in range(rows + 1):
        y = y0 + r * row_h
        page.draw_line((x0, y), (x0 + cols * col_w, y))
    for c in range(cols + 1):
        x = x0 + c * col_w
        page.draw_line((x, y0), (x, y0 + rows * row_h))

    # Header row
    headers = ["Name", "Type", "Status", "Notes"]
    for c, h in enumerate(headers):
        page.insert_text((x0 + c * col_w + 5, y0 + 18), h, fontsize=10)

    # Data rows
    data = [
        ["Alice", "Admin", "Active", "Lead"],
        ["Bob", "User", "Inactive", "New"],
    ]
    for r, row_data in enumerate(data):
        for c, val in enumerate(row_data):
            page.insert_text((x0 + c * col_w + 5, y0 + (r + 1) * row_h + 18), val, fontsize=10)

    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def multi_page_pdf(tmp_path):
    """Create a PDF with text page + table page."""
    import pymupdf
    path = str(tmp_path / "multi.pdf")
    doc = pymupdf.open()

    # Page 0: text
    page0 = doc.new_page(width=612, height=792)
    page0.insert_text((72, 72), "This is a text-only page.", fontsize=12)

    # Page 1: table
    page1 = doc.new_page(width=612, height=792)
    x0, y0 = 72, 72
    cols, rows = 3, 4
    col_w, row_h = 150, 30
    for r in range(rows + 1):
        y = y0 + r * row_h
        page1.draw_line((x0, y), (x0 + cols * col_w, y))
    for c in range(cols + 1):
        x = x0 + c * col_w
        page1.draw_line((x, y0), (x, y0 + rows * row_h))
    for r in range(rows):
        for c in range(cols):
            page1.insert_text(
                (x0 + c * col_w + 5, y0 + r * row_h + 18),
                f"Cell{r}{c}",
                fontsize=9,
            )

    doc.save(path)
    doc.close()
    return path


class TestExtractTablesFromPages:
    def test_table_extraction(self, simple_table_pdf):
        md = extract_tables_from_pages(simple_table_pdf, [0])
        assert "|" in md
        assert "---" in md
        # Should contain header values
        assert "Name" in md or "Type" in md

    def test_text_page_fallback(self, multi_page_pdf):
        """Text-only page should produce some output (plain text fallback)."""
        md = extract_tables_from_pages(multi_page_pdf, [0])
        assert "text" in md.lower()

    def test_table_page(self, multi_page_pdf):
        md = extract_tables_from_pages(multi_page_pdf, [1])
        assert "|" in md
        assert "Cell" in md

    def test_empty_pages_list(self, simple_table_pdf):
        md = extract_tables_from_pages(simple_table_pdf, [])
        assert md.strip() == ""


class TestCleanCell:
    def test_none(self):
        assert _clean_cell(None) == ""

    def test_string(self):
        assert _clean_cell("hello") == "hello"

    def test_whitespace(self):
        assert _clean_cell("  hello  ") == "hello"

    def test_newlines(self):
        assert _clean_cell("line1\nline2") == "line1 line2"

    def test_pipe_escape(self):
        assert _clean_cell("a|b") == "a\\|b"

    def test_number(self):
        assert _clean_cell(42) == "42"
