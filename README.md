# Split PDF to MD

Split large PDFs via natural language descriptions and convert to LLM-optimized Markdown.

```
[PDF + natural language] -> [page range parsing] -> [PDF split] -> [MD conversion] -> [optimized .md files]
```

## Features

- **Natural language splitting** - Describe how to split: `"1-500 intro, 501-1000 methods"` or `"split by chapters"`
- **Smart fast path** - Explicit page ranges are parsed instantly via regex (no API call needed)
- **LLM parsing** - Semantic descriptions analyzed by Claude with PDF structure context (bookmarks, TOC, page sampling)
- **Dual MD engine** - `marker-pdf` (high-quality tables/formulas) or `pymupdf4llm` (lightweight/fast), auto-fallback
- **Token optimization** - Post-processing removes headers/footers, page numbers, fixes broken lines, normalizes whitespace
- **Reusable ranges** - Parsed ranges saved as `ranges.json` for re-runs without API calls

## Quick Start

### Install

```bash
# Lite (recommended)
pip install -r requirements-lite.txt

# Full (includes marker-pdf, requires torch ~2GB)
pip install -r requirements-full.txt
```

### Run

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Split + convert (explicit ranges, no API call needed)
python -m src.main --pdf book.pdf --desc "1-500 intro, 501-1500 methods, 1501-3000 results"

# Split only
python -m src.main --pdf book.pdf --desc "1-500, 501-1000" --split-only

# Semantic description (uses Claude API)
python -m src.main --pdf book.pdf --desc "Split by chapters"

# Reuse saved ranges
python -m src.main --pdf book.pdf --ranges output/ranges.json

# Convert existing PDFs
python -m src.main --convert-dir ./pdf_chunks/ --converter pymupdf4llm
```

### Output

```
output/
├── ranges.json           # Parsed page ranges (reusable)
├── chunks/
│   ├── 01_intro.pdf
│   ├── 02_methods.pdf
│   └── 03_results.pdf
└── markdown/
    ├── 01_intro.md
    ├── 02_methods.md
    └── 03_results.md
```

## CLI Reference

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--pdf` | `-p` | | Input PDF path |
| `--desc` | `-d` | | Natural language page range description |
| `--output` | `-o` | `./output` | Output directory |
| `--ranges` | `-r` | | Pre-existing ranges.json (skip LLM) |
| `--convert-dir` | | | Convert-only mode: directory of PDFs |
| `--converter` | `-c` | `auto` | Engine: `auto`, `marker`, `pymupdf4llm` |
| `--model` | `-m` | `claude-sonnet-4-20250514` | Claude model ID |
| `--toc-pages` | | `30` | Pages to scan for TOC |
| `--no-postprocess` | | | Skip MD token optimization |
| `--split-only` | | | Only split PDF, skip conversion |
| `--verbose` | `-v` | | Verbose logging |

## Page Range Formats

**Fast path** (regex, no API call):
```
1-500, 501-1000               # comma-separated
1-100 intro, 101-500 methods  # with labels
1~500, 501~1000               # tilde
1到500, 501至1000              # Chinese
```

**LLM path** (requires `ANTHROPIC_API_KEY`):
```
"Split by chapters"
"First 100 pages as intro, rest as main content"
"Separate the appendix from the main text"
```

## Docker

```bash
# Lite image (~250MB, pymupdf4llm only)
docker compose --profile lite run pdf-processor-lite \
  --pdf /app/input/book.pdf --desc "1-500, 501-1000"

# Full image (~2.5GB, includes marker-pdf)
docker compose --profile full run pdf-processor \
  --pdf /app/input/book.pdf --desc "1-500, 501-1000" --converter marker
```

Place PDFs in `./input/`, results appear in `./output/`.

Set your API key in `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

## Converter Comparison

| Engine | Size | Speed | Tables/Formulas | Best for |
|--------|------|-------|----------------|----------|
| `pymupdf4llm` | ~50MB | Fast | Basic | Text-heavy PDFs |
| `marker-pdf` | ~2GB | Slower | High quality | Complex layouts, scanned docs |

`auto` mode tries marker first, falls back to pymupdf4llm if not installed.

## Token Optimization

The post-processor reduces token usage by:

| Step | Savings | Description |
|------|---------|-------------|
| Header/footer removal | 5-15% | Detects repeated text across page boundaries |
| Page number removal | 1-3% | Removes standalone page numbers |
| Broken line fix | 10-20% | Rejoins mid-sentence line breaks from PDF extraction |
| Whitespace normalization | 3-5% | Collapses blank lines, trims trailing spaces |

Disable with `--no-postprocess`.

## Development

```bash
pip install pypdf anthropic pyyaml tqdm pymupdf4llm pymupdf pytest pytest-cov ruff

# Run tests
python -m pytest tests/ -v

# Lint
ruff check src/ tests/
```

## Project Structure

```
src/
├── main.py              # CLI entry + pipeline orchestration
├── config.py            # Configuration management
├── toc_scanner.py       # PDF structure scanning (3-layer)
├── range_extractor.py   # Page range parsing (regex + LLM)
├── pdf_splitter.py      # PDF splitting (pypdf)
├── pdf_to_md.py         # Dual-engine MD converter
├── md_postprocess.py    # Token optimization post-processor
└── utils.py             # Shared utilities
```
