#!/usr/bin/env python3
"""Split PDF to MD - CLI entry point and pipeline orchestration."""
from __future__ import annotations

import os
import sys
import time

from .config import AppConfig, load_config, validate_config
from .range_extractor import extract_ranges, save_ranges, load_ranges, PageRange
from .pdf_splitter import split_pdf
from .pdf_to_md import PDFConverter, ConvertResult
from .md_postprocess import PostprocessConfig
from .utils import setup_logging


def run_pipeline(config: AppConfig) -> int:
    """Execute the pipeline. Returns exit code."""
    logger = setup_logging(config.verbose)

    # Validate
    errors = validate_config(config)
    if errors:
        for e in errors:
            logger.error(e)
        return 1

    start_time = time.time()

    try:
        # Convert-dir mode: skip split, just convert existing PDFs
        if config.convert_dir:
            return _run_convert_only(config, logger, start_time)

        # Step 1: Get page ranges
        ranges = _resolve_ranges(config, logger)
        if not ranges:
            return 3

        # Save ranges for reuse
        ranges_path = os.path.join(config.output_dir, "ranges.json")
        os.makedirs(config.output_dir, exist_ok=True)
        save_ranges(ranges, ranges_path)

        # Step 2: Split PDF
        chunks_dir = os.path.join(config.output_dir, "chunks")
        logger.info(f"Splitting PDF into {len(ranges)} parts...")
        output_files = split_pdf(config.pdf_path, ranges, chunks_dir)

        # Step 3: Convert to MD
        md_results = []
        if not config.split_only:
            md_results = _convert_to_md(config, output_files, logger)

        # Summary
        elapsed = time.time() - start_time
        _print_summary(ranges, output_files, md_results, elapsed)
        return 0

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 2
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=config.verbose)
        return 4


def _run_convert_only(config: AppConfig, logger, start_time: float) -> int:
    """Convert-dir mode: convert existing PDFs without splitting."""
    pdf_files = sorted(
        os.path.join(config.convert_dir, f)
        for f in os.listdir(config.convert_dir)
        if f.lower().endswith(".pdf")
    )
    if not pdf_files:
        logger.error(f"No PDF files found in {config.convert_dir}")
        return 2

    md_results = _convert_to_md(config, pdf_files, logger)
    elapsed = time.time() - start_time

    print(f"\nConverted {len(md_results)} files in {elapsed:.1f}s")
    for r in md_results:
        print(f"  {os.path.basename(r.md_path)}: {r.size_bytes / 1024:.0f} KB [{r.converter_used}]")
    return 0


def _convert_to_md(
    config: AppConfig, pdf_files: list[str], logger
) -> list[ConvertResult]:
    """Convert split PDFs to Markdown."""
    pp_config = PostprocessConfig() if not config.no_postprocess else PostprocessConfig(
        remove_headers_footers=False,
        remove_page_numbers=False,
        normalize_whitespace=False,
        fix_broken_lines=False,
    )

    converter = PDFConverter(
        converter=config.converter,
        postprocess=not config.no_postprocess,
        postprocess_config=pp_config,
    )

    md_dir = os.path.join(config.output_dir, "markdown")
    logger.info(f"Converting {len(pdf_files)} PDFs to Markdown ({config.converter})...")
    return converter.convert_batch(pdf_files, md_dir)


def _resolve_ranges(config: AppConfig, logger) -> list[PageRange] | None:
    """Resolve page ranges from file or extraction."""
    if config.ranges_file:
        logger.info(f"Loading ranges from {config.ranges_file}")
        return load_ranges(config.ranges_file)

    logger.info("Extracting page ranges from description...")
    return extract_ranges(
        pdf_path=config.pdf_path,
        natural_desc=config.natural_desc,
        api_key=config.anthropic_api_key,
        model=config.model,
        max_tokens=config.max_tokens,
        toc_scan_pages=config.toc_scan_pages,
    )


def _print_summary(
    ranges: list[PageRange],
    output_files: list[str],
    md_results: list[ConvertResult],
    elapsed: float,
):
    total_pages = sum(r.page_count() for r in ranges)
    pdf_size = sum(os.path.getsize(f) for f in output_files) / (1024 * 1024)
    md_size = sum(r.size_bytes for r in md_results) / (1024 * 1024) if md_results else 0

    print("\n" + "=" * 60)
    print("Pipeline Complete")
    print("=" * 60)
    print(f"  Parts:        {len(ranges)}")
    print(f"  Total pages:  {total_pages}")
    print(f"  PDF size:     {pdf_size:.1f} MB")
    if md_results:
        print(f"  MD size:      {md_size:.1f} MB")
        token_est = sum(r.size_bytes for r in md_results) // 4
        print(f"  Token est:    ~{token_est:,}")
    print(f"  Time:         {elapsed:.1f}s")
    print()
    for i, (rg, path) in enumerate(zip(ranges, output_files), 1):
        pdf_s = os.path.getsize(path) / (1024 * 1024)
        line = f"  {i:2d}. {rg.name} (p.{rg.start_page}-{rg.end_page}, {rg.page_count()} pages, {pdf_s:.1f} MB PDF"
        if i <= len(md_results):
            md_s = md_results[i - 1].size_bytes / 1024
            line += f", {md_s:.0f} KB MD [{md_results[i - 1].converter_used}]"
        line += ")"
        print(line)
    print("=" * 60)


def main():
    config = load_config()
    sys.exit(run_pipeline(config))


if __name__ == "__main__":
    main()
