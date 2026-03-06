---
name: split-pdf-to-md
description: Split large PDF documents by functional sections and convert to LLM-optimized Markdown. Use when user wants to split/chunk a PDF, convert PDF to markdown, or prepare PDF content for LLM consumption.
triggers:
  - split pdf
  - pdf to md
  - pdf to markdown
  - chunk pdf
  - pdf split
  - split document
---

# Split PDF to MD Skill

## When to use
- User has a large PDF and wants it split by sections/chapters/functions
- User wants to convert PDF to Markdown for LLM use
- User mentions "split pdf", "pdf to md", "chunk pdf", or similar

## Prerequisites
- Project located at `/mnt/c/repo/ai-split-pdf-to-md/`
- Python packages: `pypdf`, `pymupdf4llm`, `pymupdf`, `anthropic` (if LLM needed)

## Workflow

### Step 1: Locate the PDF
- Ask user for the PDF path if not provided
- Check file exists and get page count:
```python
from pypdf import PdfReader
reader = PdfReader("<pdf_path>")
print(f"Total pages: {len(reader.pages)}")
```

### Step 2: Scan PDF structure
- Use the project's toc_scanner to extract bookmarks and identify sections:
```bash
cd /mnt/c/repo/ai-split-pdf-to-md
python3 -c "
from src.toc_scanner import scan_toc
info = scan_toc('<pdf_path>', scan_pages=50)
print(f'Bookmarks: {len(info.bookmarks)}')
for bm in info.bookmarks:
    if bm.level <= 1:
        indent = '  ' * bm.level
        print(f'{indent}[p.{bm.page}] {bm.title}')
"
```

### Step 3: Build page ranges
- From the bookmarks, identify top-level sections (level == 0)
- Calculate each section's page range: start = current section's page, end = next section's page - 1
- Last section ends at total_pages
- For tiny sections (1-2 pages like "Wireless" + "Switch Controller"), consider merging with neighbors
- Build a Python script to create PageRange objects and save to JSON:
```python
from src.range_extractor import PageRange, save_ranges
ranges = [
    PageRange("01_Section_Name", start_page, end_page, "reason"),
    # ...
]
save_ranges(ranges, "<output_dir>/ranges.json")
```

### Step 4: Execute split
```bash
python3 -m src.main \
  --pdf <pdf_path> \
  --ranges <output_dir>/ranges.json \
  --output <output_dir> \
  --split-only \
  --verbose
```

### Step 5: Convert to Markdown
```bash
python3 -m src.main \
  --convert-dir <output_dir>/chunks \
  --output <output_dir> \
  --converter pymupdf4llm \
  --verbose
```
- Use `pymupdf4llm` by default (fast, lightweight)
- Use `marker` only if user specifically needs high-quality table/formula extraction

### Step 6: Verify conversion quality
- Spot-check a few MD files, especially short ones (< 5 pages) which are most prone to content loss
- Compare MD content against the source PDF to ensure tables, lists, and body text are present
- The converter has a built-in content integrity check (plain text fallback when >40% content is lost), but always verify manually on at least 2-3 files
- If a file looks incomplete, re-convert that single file with `--no-postprocess` to rule out post-processing issues

### Step 7: Copy results and write report
- Copy markdown files to `results/` with clean names (strip leading number prefix):
```bash
mkdir -p results
for f in output/markdown/*.md; do
  basename="${f##*/}"; newname="${basename#*_}"
  cp "$f" "results/${newname}"
done
```
- Write `results/SPLIT_REPORT.md` with a summary table:

```markdown
| # | Function | Pages | PDF | MD |
|---|----------|-------|-----|-----|
| 01 | Section Name | N | XM | YK |
```

Include: source filename, total pages, compression ratio, timing, output paths.

## Key Lessons from Production Use

1. **Always scan bookmarks first** - Most technical PDFs have bookmarks (reader.outline). This is far more reliable than regex TOC scanning.

2. **Split and convert separately** - Run `--split-only` first, then `--convert-dir`. This way if conversion fails on one file, the splits are preserved and you can retry.

3. **Use level-0 bookmarks as split boundaries** - Top-level bookmarks map to functional sections. Don't go deeper (level 1+) or you'll get too many tiny files.

4. **Merge tiny sections** - Sections with 1-2 pages (like "Wireless configuration" + "Switch Controller") should be merged with neighbors.

5. **Calculate end_page as next_section_start - 1** - Not all content falls neatly under bookmarks; pages between sections belong to the prior section.

6. **pymupdf4llm is the practical default** - marker-pdf requires torch (~2GB), is slower, and often unnecessary for text-heavy technical docs. Use pymupdf4llm unless tables/formulas are critical.

7. **~95% size reduction is typical** - Technical PDFs with screenshots compress dramatically (134MB PDF -> 6.5MB MD). Estimate ~1.5KB MD per page for text-heavy content.

8. **Conversion speed** - Expect ~10 pages/sec with pymupdf4llm. A 4600-page doc takes ~7-8 minutes.

9. **Front matter pages** - Skip the first N pages (cover, TOC, copyright) by starting ranges from the first real content bookmark, not page 1.

10. **Always save ranges.json** - This allows re-running conversion without re-analyzing structure. Critical for iterating on post-processing settings.

11. **Content loss with pymupdf4llm** - The default `lines_strict` table strategy relies on graphic lines to detect tables. Some PDFs draw tables with invisible or non-standard lines, causing pymupdf4llm to skip the entire table area's text. The converter now has a built-in fallback: it compares markdown output length vs raw `get_text()` length, and if <60% is preserved, it falls back to plain text extraction. Short sections (1-5 pages) are most at risk — always spot-check them.

12. **Post-processing can remove valid content** - The header/footer remover and page number remover use heuristics. On very short documents (1-3 pages), a legitimate line might match a page number pattern. When in doubt, use `--no-postprocess` and verify.

13. **Verify before delivering** - After conversion, always spot-check at least the shortest and longest MD files against their PDF source. Content loss is silent — the tool won't error, it just produces a smaller file.
