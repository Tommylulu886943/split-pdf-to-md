import os
import pytest
from pypdf import PdfReader

from src.range_extractor import PageRange
from src.pdf_splitter import split_pdf


class TestSplitPdf:
    def test_basic_split(self, sample_pdf, tmp_path):
        ranges = [
            PageRange("first", 1, 5),
            PageRange("second", 6, 10),
        ]
        output_dir = str(tmp_path / "chunks")
        result = split_pdf(sample_pdf, ranges, output_dir)

        assert len(result) == 2
        assert all(os.path.exists(p) for p in result)

        reader1 = PdfReader(result[0])
        assert len(reader1.pages) == 5

        reader2 = PdfReader(result[1])
        assert len(reader2.pages) == 5

    def test_single_page_range(self, sample_pdf, tmp_path):
        ranges = [PageRange("single", 3, 3)]
        output_dir = str(tmp_path / "chunks")
        result = split_pdf(sample_pdf, ranges, output_dir)

        assert len(result) == 1
        reader = PdfReader(result[0])
        assert len(reader.pages) == 1

    def test_non_contiguous_ranges(self, sample_pdf, tmp_path):
        ranges = [
            PageRange("part1", 1, 3),
            PageRange("part2", 7, 10),
        ]
        output_dir = str(tmp_path / "chunks")
        result = split_pdf(sample_pdf, ranges, output_dir)

        assert len(result) == 2
        assert len(PdfReader(result[0]).pages) == 3
        assert len(PdfReader(result[1]).pages) == 4

    def test_filename_format(self, sample_pdf, tmp_path):
        ranges = [PageRange("my section", 1, 5)]
        output_dir = str(tmp_path / "chunks")
        result = split_pdf(sample_pdf, ranges, output_dir)

        filename = os.path.basename(result[0])
        assert filename == "01_my_section.pdf"

    def test_exceeds_total_pages(self, sample_pdf, tmp_path):
        ranges = [PageRange("bad", 1, 999)]
        output_dir = str(tmp_path / "chunks")
        with pytest.raises(ValueError, match="exceeds total pages"):
            split_pdf(sample_pdf, ranges, output_dir)

    def test_progress_callback(self, sample_pdf, tmp_path):
        ranges = [
            PageRange("a", 1, 5),
            PageRange("b", 6, 10),
        ]
        output_dir = str(tmp_path / "chunks")
        progress_calls = []
        split_pdf(sample_pdf, ranges, output_dir, on_progress=lambda c, t, f: progress_calls.append((c, t, f)))

        assert len(progress_calls) == 2
        assert progress_calls[0][0] == 1  # current
        assert progress_calls[1][0] == 2
        assert progress_calls[0][1] == 2  # total

    def test_creates_output_dir(self, sample_pdf, tmp_path):
        output_dir = str(tmp_path / "nested" / "dir" / "chunks")
        ranges = [PageRange("a", 1, 5)]
        result = split_pdf(sample_pdf, ranges, output_dir)
        assert os.path.isdir(output_dir)
        assert len(result) == 1
