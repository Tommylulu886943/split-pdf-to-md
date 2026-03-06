import os
import pytest
from pypdf import PdfWriter


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a 10-page sample PDF for testing."""
    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    for i in range(10):
        writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        writer.write(f)
    return str(path)


@pytest.fixture
def sample_pdf_20(tmp_path):
    """Create a 20-page sample PDF."""
    path = tmp_path / "sample20.pdf"
    writer = PdfWriter()
    for i in range(20):
        writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        writer.write(f)
    return str(path)
