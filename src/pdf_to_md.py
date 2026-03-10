"""PDF to Markdown converter with dual engine support."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable

from .md_postprocess import postprocess_md, PostprocessConfig

logger = logging.getLogger("split-pdf")


@dataclass
class ConvertResult:
    md_path: str
    page_count: int
    size_bytes: int
    converter_used: str
    warnings: list[str] = field(default_factory=list)


class PDFConverter:
    """PDF to Markdown converter with marker (primary) and pymupdf4llm (fallback)."""

    def __init__(
        self,
        converter: str = "auto",
        postprocess: bool = True,
        postprocess_config: PostprocessConfig | None = None,
    ):
        """
        Args:
            converter: "marker", "pymupdf4llm", or "auto" (try marker then fallback).
            postprocess: Whether to run MD post-processing.
            postprocess_config: Post-processing options.
        """
        self.converter = converter
        self.postprocess = postprocess
        self.postprocess_config = postprocess_config or PostprocessConfig()
        self._resolved_converter: str | None = None

    def convert(self, pdf_path: str, output_md: str) -> ConvertResult:
        """
        Convert a PDF file to Markdown.

        Args:
            pdf_path: Input PDF path.
            output_md: Output Markdown path.

        Returns:
            ConvertResult with metadata.
        """
        os.makedirs(os.path.dirname(output_md) or ".", exist_ok=True)

        warnings = []
        raw_md, converter_used, page_count = self._do_convert(pdf_path, warnings)

        if self.postprocess:
            raw_md = postprocess_md(raw_md, self.postprocess_config)

        with open(output_md, "w", encoding="utf-8") as f:
            f.write(raw_md)

        size = os.path.getsize(output_md)
        logger.info(
            f"{os.path.basename(output_md)}: {page_count} pages, "
            f"{size / 1024:.0f} KB ({converter_used})"
        )

        return ConvertResult(
            md_path=output_md,
            page_count=page_count,
            size_bytes=size,
            converter_used=converter_used,
            warnings=warnings,
        )

    def convert_batch(
        self,
        pdf_files: list[str],
        output_dir: str,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[ConvertResult]:
        """Convert multiple PDFs to Markdown."""
        os.makedirs(output_dir, exist_ok=True)
        results = []

        for i, pdf_path in enumerate(pdf_files, 1):
            basename = os.path.splitext(os.path.basename(pdf_path))[0]
            md_path = os.path.join(output_dir, f"{basename}.md")

            try:
                result = self.convert(pdf_path, md_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to convert {os.path.basename(pdf_path)}: {e}")
                results.append(ConvertResult(
                    md_path=md_path,
                    page_count=0,
                    size_bytes=0,
                    converter_used="error",
                    warnings=[f"Conversion failed: {e}"],
                ))

            if on_progress:
                on_progress(i, len(pdf_files), os.path.basename(md_path))

        return results

    def _do_convert(
        self, pdf_path: str, warnings: list[str]
    ) -> tuple[str, str, int]:
        """
        Execute conversion. Returns (markdown_text, converter_name, page_count).
        """
        if self.converter == "marker":
            return self._convert_marker(pdf_path, warnings)
        elif self.converter == "pymupdf4llm":
            return self._convert_pymupdf4llm(pdf_path, warnings)
        else:  # auto
            return self._convert_auto(pdf_path, warnings)

    def _convert_auto(
        self, pdf_path: str, warnings: list[str]
    ) -> tuple[str, str, int]:
        """Try marker first, fall back to pymupdf4llm."""
        try:
            return self._convert_marker(pdf_path, warnings)
        except ImportError:
            logger.info("marker-pdf not available, falling back to pymupdf4llm")
            warnings.append("marker-pdf not installed, used pymupdf4llm fallback")
            return self._convert_pymupdf4llm(pdf_path, warnings)
        except Exception as e:
            logger.warning(f"marker-pdf failed ({e}), falling back to pymupdf4llm")
            warnings.append(f"marker-pdf error: {e}, used pymupdf4llm fallback")
            return self._convert_pymupdf4llm(pdf_path, warnings)

    def _convert_marker(
        self, pdf_path: str, warnings: list[str]
    ) -> tuple[str, str, int]:
        """Convert using marker-pdf."""
        try:
            from marker.converters.pdf import PdfConverter as MarkerConverter
            from marker.config.parser import ConfigParser
        except ImportError:
            raise ImportError(
                "marker-pdf is not installed. Install with: pip install marker-pdf"
            )

        config_parser = ConfigParser({"output_format": "markdown"})
        converter = MarkerConverter(config=config_parser.generate_config_dict())
        rendered = converter(pdf_path)
        markdown_text = rendered.markdown

        # Get page count from pypdf (marker doesn't expose it directly)
        from pypdf import PdfReader
        page_count = len(PdfReader(pdf_path).pages)

        return markdown_text, "marker", page_count

    def _convert_pymupdf4llm(
        self, pdf_path: str, warnings: list[str]
    ) -> tuple[str, str, int]:
        """Convert using pymupdf4llm with content integrity check."""
        try:
            import pymupdf4llm
            import pymupdf
        except ImportError:
            raise ImportError(
                "pymupdf4llm is not installed. Install with: pip install pymupdf4llm pymupdf"
            )

        doc = pymupdf.open(pdf_path)
        page_count = len(doc)

        # Get raw text length for integrity comparison
        raw_text_len = sum(len(page.get_text()) for page in doc)

        # Primary: lines_strict (best for well-structured tables)
        md_text = pymupdf4llm.to_markdown(
            pdf_path,
            show_progress=False,
            force_text=True,
        )

        # Content integrity check: if markdown lost >40% of raw text,
        # the default lines_strict table strategy likely missed table content.
        # Fall back to plain text which preserves all content reliably.
        md_content_len = len(md_text)
        if raw_text_len > 0 and md_content_len < raw_text_len * 0.6:
            logger.debug(
                f"Content loss detected ({md_content_len}/{raw_text_len} chars), "
                f"using plain text fallback"
            )
            md_text = _plain_text_to_md(doc)
            warnings.append("Used plain text fallback due to table extraction issues")

        doc.close()
        return md_text, "pymupdf4llm", page_count


def _plain_text_to_md(doc) -> str:
    """Fallback: extract plain text from pymupdf document and format as markdown."""
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if text:
            pages.append(text)
    return "\n\n---\n\n".join(pages) + "\n"
