"""Integration tests for the full pipeline."""
import json
import os
import pytest
import pymupdf

from src.config import AppConfig
from src.main import run_pipeline


@pytest.fixture
def integration_pdf(tmp_path):
    """Create a 10-page PDF with text content."""
    path = str(tmp_path / "integration.pdf")
    doc = pymupdf.open()
    for i in range(10):
        page = doc.new_page(width=612, height=792)
        page.insert_text(
            (72, 72),
            f"Chapter {i + 1}\n\nThis is the content of page {i + 1}.\n"
            f"It contains important information about topic {i + 1}.",
            fontsize=12,
        )
    doc.save(path)
    doc.close()
    return path


class TestFullPipeline:
    def test_split_only(self, integration_pdf, tmp_path):
        output_dir = str(tmp_path / "output")
        config = AppConfig(
            pdf_path=integration_pdf,
            natural_desc="1-5, 6-10",
            output_dir=output_dir,
            split_only=True,
        )
        exit_code = run_pipeline(config)
        assert exit_code == 0

        # Check ranges.json
        ranges_path = os.path.join(output_dir, "ranges.json")
        assert os.path.exists(ranges_path)
        with open(ranges_path) as f:
            ranges = json.load(f)
        assert len(ranges) == 2

        # Check chunk PDFs
        chunks_dir = os.path.join(output_dir, "chunks")
        pdfs = [f for f in os.listdir(chunks_dir) if f.endswith(".pdf")]
        assert len(pdfs) == 2

        # No markdown dir should exist
        md_dir = os.path.join(output_dir, "markdown")
        assert not os.path.exists(md_dir)

    def test_full_pipeline_with_conversion(self, integration_pdf, tmp_path):
        output_dir = str(tmp_path / "output")
        config = AppConfig(
            pdf_path=integration_pdf,
            natural_desc="1-5 intro, 6-10 conclusion",
            output_dir=output_dir,
            converter="pymupdf4llm",
        )
        exit_code = run_pipeline(config)
        assert exit_code == 0

        # Check chunk PDFs
        chunks_dir = os.path.join(output_dir, "chunks")
        pdfs = sorted(os.listdir(chunks_dir))
        assert len(pdfs) == 2

        # Check markdown files
        md_dir = os.path.join(output_dir, "markdown")
        mds = sorted(os.listdir(md_dir))
        assert len(mds) == 2
        assert all(f.endswith(".md") for f in mds)

        # Check MD content
        with open(os.path.join(md_dir, mds[0]), "r") as f:
            content = f.read()
        assert len(content) > 0

    def test_ranges_file_reuse(self, integration_pdf, tmp_path):
        # First run: generate ranges
        output_dir = str(tmp_path / "output")
        config = AppConfig(
            pdf_path=integration_pdf,
            natural_desc="1-3, 4-7, 8-10",
            output_dir=output_dir,
            split_only=True,
        )
        run_pipeline(config)

        # Second run: reuse ranges
        output_dir2 = str(tmp_path / "output2")
        ranges_path = os.path.join(output_dir, "ranges.json")
        config2 = AppConfig(
            pdf_path=integration_pdf,
            ranges_file=ranges_path,
            output_dir=output_dir2,
            split_only=True,
        )
        exit_code = run_pipeline(config2)
        assert exit_code == 0

        chunks = os.listdir(os.path.join(output_dir2, "chunks"))
        assert len(chunks) == 3

    def test_convert_dir_mode(self, integration_pdf, tmp_path):
        # First: split
        split_dir = str(tmp_path / "split_output")
        config1 = AppConfig(
            pdf_path=integration_pdf,
            natural_desc="1-5, 6-10",
            output_dir=split_dir,
            split_only=True,
        )
        run_pipeline(config1)

        # Then: convert-dir
        chunks_dir = os.path.join(split_dir, "chunks")
        convert_output = str(tmp_path / "convert_output")
        config2 = AppConfig(
            convert_dir=chunks_dir,
            output_dir=convert_output,
            converter="pymupdf4llm",
        )
        exit_code = run_pipeline(config2)
        assert exit_code == 0

    def test_no_postprocess(self, integration_pdf, tmp_path):
        output_dir = str(tmp_path / "output")
        config = AppConfig(
            pdf_path=integration_pdf,
            natural_desc="1-5, 6-10",
            output_dir=output_dir,
            converter="pymupdf4llm",
            no_postprocess=True,
        )
        exit_code = run_pipeline(config)
        assert exit_code == 0

    def test_invalid_pdf_path(self, tmp_path):
        config = AppConfig(
            pdf_path="/nonexistent.pdf",
            natural_desc="1-5",
            output_dir=str(tmp_path / "output"),
        )
        exit_code = run_pipeline(config)
        assert exit_code == 1

    def test_labeled_ranges_filenames(self, integration_pdf, tmp_path):
        output_dir = str(tmp_path / "output")
        config = AppConfig(
            pdf_path=integration_pdf,
            natural_desc="1-5 intro, 6-10 conclusion",
            output_dir=output_dir,
            converter="pymupdf4llm",
        )
        run_pipeline(config)

        md_dir = os.path.join(output_dir, "markdown")
        mds = sorted(os.listdir(md_dir))
        assert "intro" in mds[0]
        assert "conclusion" in mds[1]
