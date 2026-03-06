# AI Split PDF to MD

## Project Overview

CLI tool to split large PDFs by functional sections and convert to LLM-optimized Markdown.

## Tech Stack

- Python 3.10+, pypdf, pymupdf4llm (lightweight) / marker-pdf (high-quality)
- Claude API (anthropic SDK) for semantic page range parsing
- Docker multi-stage: lite (~250MB) / full (~2.5GB)

## Key Files

- `src/main.py` - CLI entry + pipeline orchestration (3 modes: full / split-only / convert-only)
- `src/config.py` - AppConfig dataclass + argparse
- `src/toc_scanner.py` - 3-layer PDF structure scan (bookmarks -> TOC detection -> sampling)
- `src/range_extractor.py` - Fast regex path + LLM fallback + JSON parse with 3-layer tolerance
- `src/pdf_splitter.py` - Pure pypdf splitting
- `src/pdf_to_md.py` - Dual engine converter (marker / pymupdf4llm / auto)
- `src/md_postprocess.py` - Token optimizer (headers/footers, page numbers, broken lines, whitespace)

## Commands

- Run tests: `python3 -m pytest tests/ -v`
- Lint: `ruff check src/ tests/`
- Run pipeline: `python3 -m src.main --pdf <file> --desc "<description>"`
