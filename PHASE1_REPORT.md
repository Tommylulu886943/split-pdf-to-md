# Phase 1 Development Report

## Summary

Phase 1 (Core Pipeline MVP) 開發完成。實現了從自然語言描述到 PDF 拆分的完整流程，包含快速路徑正則解析、LLM 語義解析、PDF 結構掃描、PDF 拆分引擎，以及 CLI 介面。

## Delivered Modules

| Module | File | Lines | Description |
|--------|------|-------|-------------|
| Config | `src/config.py` | 72 | AppConfig dataclass + CLI argparse + 驗證 |
| TOC Scanner | `src/toc_scanner.py` | 131 | 三層 PDF 結構掃描 (bookmarks → TOC detection → sampling) |
| Range Extractor | `src/range_extractor.py` | 199 | 快速路徑正則 + LLM 解析 + JSON 容錯 + 驗證 |
| PDF Splitter | `src/pdf_splitter.py` | 62 | pypdf 拆分 + 驗證 + progress callback |
| Main Pipeline | `src/main.py` | 89 | CLI 入口 + pipeline 編排 + summary 輸出 |
| Utils | `src/utils.py` | 18 | logging setup + filename sanitization |

## Test Results

```
43 passed in 1.16s
```

| Test File | Tests | Coverage Focus |
|-----------|-------|---------------|
| `test_config.py` | 13 | CLI 參數解析、預設值、環境變數、驗證邏輯 |
| `test_range_extractor.py` | 22 | 快速路徑 11 格式、JSON 容錯 4 場景、驗證 6 邊界、序列化 roundtrip |
| `test_pdf_splitter.py` | 7 | 基本拆分、單頁、非連續、檔名、越界、callback、目錄建立 |

## Architecture Decisions Made

### 1. Fast Path Regex (zero-cost for explicit ranges)

當描述為明確頁範圍時（如 `"1-100, 101-500"`），直接正則解析，不呼叫 LLM。

支持的格式：
- 數字範圍: `100-500`, `100~500`, `100到500`, `100至500`
- 分隔符: `,` `，` `;` `；` 空格
- 可選標籤: `1-100 介紹, 101-500 方法`
- 前綴文字: `拆成三本: 1-100, 101-200, 201-300`

**自動 fallback**: 正則匹配失敗（頁碼越界、重疊、格式不明確）時自動進入 LLM 路徑。

### 2. Three-Layer TOC Scanning

```
Strategy 1: PDF Bookmarks (reader.outline)
    ↓ (if empty)
Strategy 2: TOC Page Detection (regex on first N pages)
    ↓ (if < 3 matches)
Strategy 3: Uniform Page Sampling (8 evenly-spaced pages)
```

每層結果都傳入 LLM prompt，但按資訊密度排序以優化 token。

### 3. Three-Layer JSON Parse Fallback

```
Layer 1: Direct json.loads(response)
    ↓ (fail)
Layer 2: Extract ```json ... ``` code fence
    ↓ (fail)
Layer 3: Extract first [...] array via regex
    ↓ (fail)
ValueError with truncated response for debugging
```

### 4. Pure pypdf (no pdftk)

移除 pdftk 外部依賴。pypdf `PdfWriter.add_page()` 對拆分場景效能足夠，且：
- 零外部二進位依賴
- Docker image 更小
- 跨平台一致性

## File Structure

```
ai-split-pdf-to-md/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── toc_scanner.py
│   ├── range_extractor.py
│   ├── pdf_splitter.py
│   └── utils.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py           (pytest fixtures: sample PDF generation)
│   ├── test_config.py
│   ├── test_range_extractor.py
│   └── test_pdf_splitter.py
├── pyproject.toml
├── requirements.txt
├── SPEC.md
└── PHASE1_REPORT.md
```

## Usage (Phase 1)

```bash
# Fast path (no LLM call needed)
python3 -m src.main --pdf input.pdf --desc "1-500, 501-1000, 1001-3000" --split-only

# With labels
python3 -m src.main --pdf input.pdf --desc "1-100 intro, 101-500 methods, 501-1000 results" --split-only

# LLM path (semantic description, requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m src.main --pdf input.pdf --desc "Split by chapters" --split-only

# Reuse saved ranges
python3 -m src.main --pdf input.pdf --ranges output/ranges.json --split-only
```

## Output Example

```
2026-03-06 22:35:00 [INFO] Fast path: parsed 3 ranges from description
2026-03-06 22:35:00 [INFO] Saved ranges to output/ranges.json
2026-03-06 22:35:00 [INFO] Splitting PDF into 3 parts...
2026-03-06 22:35:02 [INFO] 01_intro.pdf: 100 pages, 12.3 MB
2026-03-06 22:35:05 [INFO] 02_methods.pdf: 400 pages, 45.1 MB
2026-03-06 22:35:10 [INFO] 03_results.pdf: 500 pages, 58.7 MB

==================================================
Pipeline Complete
==================================================
  Parts:       3
  Total pages: 1000
  Total size:  116.1 MB
  Time:        10.3s

   1. intro (p.1-100, 100 pages, 12.3 MB)
   2. methods (p.101-500, 400 pages, 45.1 MB)
   3. results (p.501-1000, 500 pages, 58.7 MB)
==================================================
```

## Phase 2 Readiness

Phase 1 為 Phase 2 (MD Conversion) 預留了：
- `config.split_only` flag — 移除後自動進入轉換流程
- `main.py` pipeline 中 Step 3 的佔位邏輯
- `pdf_splitter.split_pdf()` 回傳 chunk 路徑列表，可直接傳入轉換器
- `pyproject.toml` 已定義 `marker` 和 `pymupdf` optional dependencies

下一步：實作 `pdf_to_md.py` (雙引擎) + `md_postprocess.py` (token 優化)。
