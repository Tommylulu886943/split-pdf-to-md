import os
import pytest
from unittest.mock import patch, MagicMock

from src.pdf_to_md import PDFConverter, ConvertResult
from src.md_postprocess import PostprocessConfig


@pytest.fixture
def text_pdf(tmp_path):
    """Create a small PDF with actual text content using pymupdf."""
    import pymupdf
    path = str(tmp_path / "text.pdf")
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Page {i + 1} content.\nThis is a test document.", fontsize=12)
    doc.save(path)
    doc.close()
    return path


class TestPDFConverterPymupdf4llm:
    def test_basic_conversion(self, text_pdf, tmp_path):
        converter = PDFConverter(converter="pymupdf4llm")
        md_path = str(tmp_path / "output.md")
        result = converter.convert(text_pdf, md_path)

        assert os.path.exists(result.md_path)
        assert result.page_count == 3
        assert result.size_bytes > 0
        assert result.converter_used == "pymupdf4llm"

        with open(md_path, "r") as f:
            content = f.read()
        assert "content" in content.lower()

    def test_postprocess_enabled(self, text_pdf, tmp_path):
        converter = PDFConverter(converter="pymupdf4llm", postprocess=True)
        md_path = str(tmp_path / "output.md")
        result = converter.convert(text_pdf, md_path)

        with open(md_path, "r") as f:
            content = f.read()
        # Should not have excessive blank lines after postprocessing
        assert "\n\n\n" not in content

    def test_postprocess_disabled(self, text_pdf, tmp_path):
        converter = PDFConverter(converter="pymupdf4llm", postprocess=False)
        md_path = str(tmp_path / "output.md")
        result = converter.convert(text_pdf, md_path)
        assert os.path.exists(result.md_path)

    def test_batch_conversion(self, text_pdf, tmp_path):
        # Create a second PDF
        import pymupdf
        pdf2 = str(tmp_path / "text2.pdf")
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Second document.")
        doc.save(pdf2)
        doc.close()

        converter = PDFConverter(converter="pymupdf4llm")
        md_dir = str(tmp_path / "md_output")
        results = converter.convert_batch([text_pdf, pdf2], md_dir)

        assert len(results) == 2
        assert all(os.path.exists(r.md_path) for r in results)

    def test_batch_progress_callback(self, text_pdf, tmp_path):
        converter = PDFConverter(converter="pymupdf4llm")
        md_dir = str(tmp_path / "md_output")
        calls = []
        converter.convert_batch(
            [text_pdf], md_dir,
            on_progress=lambda c, t, f: calls.append((c, t, f))
        )
        assert len(calls) == 1
        assert calls[0][0] == 1


class TestPDFConverterAuto:
    def test_auto_falls_back_to_pymupdf4llm(self, text_pdf, tmp_path):
        """When marker is not installed, auto mode should use pymupdf4llm."""
        converter = PDFConverter(converter="auto")
        md_path = str(tmp_path / "output.md")

        # marker likely not installed in test env, so auto should fallback
        result = converter.convert(text_pdf, md_path)
        assert result.converter_used in ("marker", "pymupdf4llm")
        assert os.path.exists(result.md_path)


class TestPDFConverterMarker:
    def test_marker_import_error(self, text_pdf, tmp_path):
        """Should raise ImportError with helpful message if marker not installed."""
        converter = PDFConverter(converter="marker")
        md_path = str(tmp_path / "output.md")

        try:
            result = converter.convert(text_pdf, md_path)
            # If marker IS installed, this should succeed
            assert result.converter_used == "marker"
        except ImportError as e:
            assert "marker-pdf" in str(e)


class TestPDFConverterContentAware:
    def test_content_aware_basic(self, text_pdf, tmp_path):
        """Content-aware mode should work on prose-only PDFs."""
        converter = PDFConverter(converter="pymupdf4llm", content_aware=True)
        md_path = str(tmp_path / "output.md")
        result = converter.convert(text_pdf, md_path)

        assert os.path.exists(result.md_path)
        assert result.page_count == 3
        assert result.size_bytes > 0
        # No tables, so should use standard pymupdf4llm
        assert "pymupdf4llm" in result.converter_used

    def test_content_aware_backward_compat(self, text_pdf, tmp_path):
        """Default (content_aware=False) should behave identically to before."""
        conv_default = PDFConverter(converter="pymupdf4llm", content_aware=False)
        conv_aware = PDFConverter(converter="pymupdf4llm", content_aware=True)

        md1 = str(tmp_path / "default.md")
        md2 = str(tmp_path / "aware.md")

        r1 = conv_default.convert(text_pdf, md1)
        r2 = conv_aware.convert(text_pdf, md2)

        # Both should succeed
        assert r1.page_count == r2.page_count
        assert r1.size_bytes > 0
        assert r2.size_bytes > 0

    def test_content_aware_with_table(self, tmp_path):
        """Content-aware should detect and handle table pages."""
        import pymupdf

        # Create PDF with table
        pdf_path = str(tmp_path / "table.pdf")
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        x0, y0 = 50, 50
        cols, rows = 4, 10
        col_w, row_h = 120, 30
        for r in range(rows + 1):
            y = y0 + r * row_h
            page.draw_line((x0, y), (x0 + cols * col_w, y))
        for c in range(cols + 1):
            x = x0 + c * col_w
            page.draw_line((x, y0), (x, y0 + rows * row_h))
        for r in range(rows):
            for c in range(cols):
                page.insert_text(
                    (x0 + c * col_w + 5, y0 + r * row_h + 18),
                    f"V{r}{c}", fontsize=8,
                )
        doc.save(pdf_path)
        doc.close()

        converter = PDFConverter(converter="pymupdf4llm", content_aware=True)
        md_path = str(tmp_path / "output.md")
        result = converter.convert(pdf_path, md_path)

        assert result.page_count == 1
        with open(md_path) as f:
            content = f.read()
        # Should contain table-like structure
        assert "|" in content or "V0" in content


class TestConvertResult:
    def test_fields(self):
        r = ConvertResult(
            md_path="/tmp/test.md",
            page_count=10,
            size_bytes=5000,
            converter_used="pymupdf4llm",
            warnings=["test warning"],
        )
        assert r.page_count == 10
        assert r.warnings == ["test warning"]
