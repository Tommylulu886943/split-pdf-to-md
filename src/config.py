from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    # Input
    pdf_path: str = ""
    natural_desc: str = ""
    output_dir: str = "./output"
    ranges_file: str | None = None  # pre-existing ranges.json
    convert_dir: str | None = None  # convert-only mode

    # LLM
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2000

    # Scanning
    toc_scan_pages: int = 30

    # Conversion
    converter: str = "auto"  # "marker" | "pymupdf4llm" | "auto"
    no_postprocess: bool = False
    content_aware: bool = False  # page-type-aware conversion

    # Modes
    split_only: bool = False

    # Logging
    verbose: bool = False


def load_config(argv: list[str] | None = None) -> AppConfig:
    parser = argparse.ArgumentParser(
        prog="split-pdf",
        description="Split PDF by natural language description and convert to Markdown",
    )
    parser.add_argument("--pdf", "-p", help="Input PDF path")
    parser.add_argument("--desc", "-d", help="Natural language page range description")
    parser.add_argument("--output", "-o", default="./output", help="Output directory")
    parser.add_argument("--ranges", "-r", help="Pre-existing ranges.json (skip LLM)")
    parser.add_argument("--convert-dir", help="Convert-only mode: directory of PDFs to convert")
    parser.add_argument("--model", "-m", help="Claude model ID")
    parser.add_argument("--toc-pages", type=int, help="Number of pages to scan for TOC")
    parser.add_argument("--converter", "-c", choices=["marker", "pymupdf4llm", "auto"],
                        default="auto", help="Conversion engine (default: auto)")
    parser.add_argument("--no-postprocess", action="store_true", help="Skip MD post-processing")
    parser.add_argument("--content-aware", action="store_true",
                        help="Enable content-aware conversion (table pages get special handling)")
    parser.add_argument("--split-only", action="store_true", help="Only split, skip MD conversion")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args(argv)

    config = AppConfig(
        pdf_path=args.pdf or "",
        natural_desc=args.desc or "",
        output_dir=args.output,
        ranges_file=args.ranges,
        convert_dir=args.convert_dir,
        converter=args.converter,
        no_postprocess=args.no_postprocess,
        content_aware=args.content_aware,
        split_only=args.split_only,
        verbose=args.verbose,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )

    if args.model:
        config.model = args.model
    if args.toc_pages is not None:
        config.toc_scan_pages = args.toc_pages

    return config


def validate_config(config: AppConfig) -> list[str]:
    """Return list of validation error messages. Empty = valid."""
    errors = []

    if config.convert_dir:
        if not os.path.isdir(config.convert_dir):
            errors.append(f"Convert directory not found: {config.convert_dir}")
        return errors

    if not config.pdf_path:
        errors.append("--pdf is required")
    elif not os.path.isfile(config.pdf_path):
        errors.append(f"PDF file not found: {config.pdf_path}")

    if not config.natural_desc and not config.ranges_file:
        errors.append("--desc or --ranges is required")

    if config.ranges_file and not os.path.isfile(config.ranges_file):
        errors.append(f"Ranges file not found: {config.ranges_file}")

    return errors
