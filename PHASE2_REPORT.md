# Phase 2 Development Report

## Summary

Phase 2 (MD Conversion + Token Optimization) 開發完成。實現了雙引擎 PDF-to-Markdown 轉換器、四步驟 token 優化後處理器，並完成完整 pipeline 整合。全部測試通過。

## Test Results

```
79 passed in 2.32s (Phase 1: 43 + Phase 2: 36 new)
```

## New Modules

| Module | File | Lines | Description |
|--------|------|-------|-------------|
| PDF→MD Converter | `src/pdf_to_md.py` | 133 | 雙引擎轉換 (marker/pymupdf4llm/auto) + batch API |
| MD Post-processor | `src/md_postprocess.py` | 163 | 四步驟 token 優化 |

## Modified Modules

| Module | Changes |
|--------|---------|
| `src/config.py` | 新增 `converter`, `no_postprocess` 欄位 + CLI 參數 |
| `src/main.py` | 整合 MD 轉換、convert-dir 模式、更新 summary 輸出 |

## New Tests

| Test File | Tests | Coverage Focus |
|-----------|-------|---------------|
| `test_md_postprocess.py` | 13 | 頁碼移除 6 場景、頁首頁尾 3 場景、斷行修復 7 場景、空白正規化 3 場景、整合 2 場景 |
| `test_pdf_to_md.py` | 7 | pymupdf4llm 轉換、後處理開關、batch 轉換、progress callback、auto fallback、marker ImportError、ConvertResult |
| `test_integration.py` | 7 | 完整 pipeline、split-only、ranges 重用、convert-dir、no-postprocess、錯誤處理、標籤檔名 |

---

## Feature Details

### 1. Dual-Engine PDF→MD Converter (`pdf_to_md.py`)

```
PDFConverter(converter="auto"|"marker"|"pymupdf4llm")
    │
    ├── marker-pdf (primary)
    │   High-quality tables/formulas, requires torch (~2GB)
    │
    └── pymupdf4llm (fallback)
        Lightweight (~50MB), fast, good for text-heavy PDFs
```

**Auto mode 邏輯：**
1. 嘗試 import marker → 成功則使用 marker
2. ImportError → 自動 fallback 到 pymupdf4llm
3. 兩者都無 → 拋出 ImportError 附安裝指令

**API：**
- `convert(pdf_path, output_md)` → `ConvertResult` — 單檔轉換
- `convert_batch(pdf_files, output_dir)` → `list[ConvertResult]` — 批次轉換 + progress callback

### 2. MD Post-processor (`md_postprocess.py`)

四個處理步驟，每個可獨立開關：

| Step | Function | Algorithm | Token 節省 |
|------|----------|-----------|-----------|
| 1. 移除重複頁首/頁尾 | `_remove_repeated_headers_footers` | 按 `---`/`\f` 分段，統計首末行頻率 >50% 則移除 | 5-15% |
| 2. 移除頁碼 | `_remove_page_numbers` | 正則匹配獨立頁碼行（`42`, `- 15 -`, `Page 7`, `p. 123`），僅移除 ≤12 字元短行 | 1-3% |
| 3. 修復斷行 | `_fix_broken_lines` | 啟發式合併：前行不以句號結尾 + 下行小寫開頭 → 合併。保護 markdown 結構（標題/列表/表格/程式碼） | 10-20% |
| 4. 正規化空白 | `_normalize_whitespace` | 合併 3+ 連續空行為 1 空行，移除行尾空白 | 3-5% |

**保護邏輯（不誤改的結構）：**
- Markdown 標題 (`#`)
- 列表項 (`-`, `*`, `+`, `1.`)
- 表格行 (`|`)
- 程式碼區塊 (`` ``` ``)
- 引用 (`>`)

### 3. Pipeline Integration

main.py 現在支持三種執行模式：

```bash
# Mode 1: Full pipeline (split + convert)
python3 -m src.main --pdf doc.pdf --desc "1-500, 501-1000" --converter pymupdf4llm

# Mode 2: Split only
python3 -m src.main --pdf doc.pdf --desc "1-500, 501-1000" --split-only

# Mode 3: Convert-dir only (existing PDFs)
python3 -m src.main --convert-dir ./pdf_chunks/ --converter pymupdf4llm
```

**新增 CLI 參數：**

| 參數 | 說明 |
|------|------|
| `--converter` / `-c` | 轉換引擎選擇：`auto` (default), `marker`, `pymupdf4llm` |
| `--no-postprocess` | 跳過 MD 後處理 |

### 4. Enhanced Summary Output

```
============================================================
Pipeline Complete
============================================================
  Parts:        2
  Total pages:  1000
  PDF size:     120.5 MB
  MD size:      2.3 MB
  Token est:    ~604,160
  Time:         45.2s

   1. intro (p.1-500, 500 pages, 65.2 MB PDF, 1280 KB MD [pymupdf4llm])
   2. conclusion (p.501-1000, 500 pages, 55.3 MB PDF, 1075 KB MD [pymupdf4llm])
============================================================
```

---

## File Structure (Complete)

```
ai-split-pdf-to-md/
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI + pipeline (3 modes)
│   ├── config.py            # AppConfig + CLI + validation
│   ├── toc_scanner.py       # 3-layer PDF structure scan
│   ├── range_extractor.py   # Fast path + LLM extraction
│   ├── pdf_splitter.py      # pypdf splitting
│   ├── pdf_to_md.py         # Dual-engine converter      [NEW]
│   ├── md_postprocess.py    # 4-step token optimizer      [NEW]
│   └── utils.py             # Logging + filename sanitize
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py       # 13 tests
│   ├── test_range_extractor.py  # 22 tests
│   ├── test_pdf_splitter.py     # 7 tests
│   ├── test_md_postprocess.py   # 13 tests               [NEW]
│   ├── test_pdf_to_md.py        # 7 tests                [NEW]
│   └── test_integration.py      # 7 tests                [NEW]
├── pyproject.toml
├── requirements.txt
├── SPEC.md
├── PHASE1_REPORT.md
└── PHASE2_REPORT.md
```

## Phase 3 Readiness

Phase 2 完成後，核心功能已全部就緒：
- 自然語言/正則 → 頁範圍解析
- PDF 拆分
- PDF → Markdown 轉換（雙引擎 + token 優化）

Phase 3 剩餘工作為部署打包：
- [ ] Dockerfile (multi-stage: full/lite)
- [ ] docker-compose.yml
- [ ] README.md
- [ ] config.example.yaml
