# Split PDF to MD - Software Development Specification

## 1. Project Overview

### 1.1 Purpose

CLI 工具，將大型 PDF 文件透過自然語言描述拆分為多個區段，並轉換為 LLM 優化的 Markdown 格式。

### 1.2 Core Pipeline

```
[PDF + 自然語言描述] → [LLM 頁範圍解析] → [PDF 拆分] → [PDF→MD 轉換] → [結構化 MD 輸出]
```

### 1.3 Scope

| In Scope | Out of Scope |
|----------|-------------|
| CLI 介面 (argparse) | Claude Skill Builder 整合 |
| LLM 頁範圍解析 (Claude API) | Web UI |
| PDF 拆分 (pypdf) | n8n workflow (未來擴展) |
| PDF→MD 轉換 (marker/pymupdf4llm) | 即時預覽 |
| Docker 部署 | 雲端儲存整合 |
| Token 優化後處理 | |

---

## 2. Architecture

### 2.1 System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    main.py (CLI)                     │
│                  argparse + config                   │
└──────────┬──────────┬──────────┬────────────────────┘
           │          │          │
           ▼          ▼          ▼
┌──────────────┐ ┌─────────┐ ┌──────────────────────┐
│ Range        │ │ PDF     │ │ PDF→MD               │
│ Extractor    │ │ Splitter│ │ Converter            │
│              │ │         │ │                      │
│ - Claude API │ │ - pypdf │ │ - marker-pdf (主)    │
│ - TOC 掃描   │ │         │ │ - pymupdf4llm (備)  │
│ - JSON 驗證  │ │         │ │ - 後處理優化         │
└──────────────┘ └─────────┘ └──────────────────────┘
           │          │          │
           ▼          ▼          ▼
┌─────────────────────────────────────────────────────┐
│              output/ 目錄                            │
│  ├── ranges.json          (解析結果，可複用)         │
│  ├── chunks/              (拆分後 PDF)               │
│  │   ├── 01_章節名.pdf                               │
│  │   └── 02_章節名.pdf                               │
│  └── markdown/            (轉換後 MD)                │
│      ├── 01_章節名.md                                │
│      └── 02_章節名.md                                │
└─────────────────────────────────────────────────────┘
```

### 2.2 Module Dependency Graph

```
main.py
  ├── config.py          (設定管理)
  ├── range_extractor.py (LLM 解析)
  │   └── toc_scanner.py (目錄掃描輔助)
  ├── pdf_splitter.py    (PDF 拆分)
  ├── pdf_to_md.py       (MD 轉換)
  │   └── md_postprocess.py (Token 優化後處理)
  └── utils.py           (共用工具)
```

---

## 3. Detailed Module Design

### 3.1 Config Management (`config.py`)

統一管理所有設定，支持 CLI 參數 > 環境變數 > 預設值的優先順序。

```python
@dataclass
class AppConfig:
    # 輸入
    pdf_path: str
    natural_desc: str          # 自然語言描述
    output_dir: str = "./output"

    # LLM
    anthropic_api_key: str     # 環境變數 ANTHROPIC_API_KEY
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2000

    # 轉換
    converter: str = "marker"  # "marker" | "pymupdf4llm"
    toc_scan_pages: int = 30   # 掃描前 N 頁尋找目錄
    ocr_enabled: bool = True

    # 後處理
    remove_headers_footers: bool = True
    remove_page_numbers: bool = True
    normalize_whitespace: bool = True
```

**設定來源優先順序：**
1. CLI 參數 (`--model`, `--converter` 等)
2. 環境變數 (`ANTHROPIC_API_KEY`, `PDF_CONVERTER` 等)
3. 專案根目錄 `config.yaml` (可選)
4. 程式碼預設值

---

### 3.2 TOC Scanner (`toc_scanner.py`)

**原方案問題：** 硬編碼掃描前 20 頁，且關鍵字匹配過於簡單（僅 "章節", "section", "chapter"），會漏掉多數實際 PDF 的目錄結構。

**優化設計：**

```python
def scan_toc(pdf_path: str, scan_pages: int = 30) -> dict:
    """
    多策略掃描 PDF 結構資訊，為 LLM 提供最佳上下文。

    回傳:
    {
        "total_pages": int,
        "bookmarks": [{"title": str, "page": int, "level": int}],
        "toc_text": str,        # 從目錄頁面擷取的文字
        "sample_pages": {       # 關鍵頁面的文字樣本
            1: "第一頁前200字...",
            15: "第15頁前200字..."
        },
        "metadata": dict        # PDF metadata (title, author 等)
    }
    """
```

**三層掃描策略（按優先順序）：**

| 策略 | 方法 | 適用場景 |
|------|------|---------|
| 1. PDF Bookmarks | `reader.outline` 提取內建書籤 | 有書籤的 PDF（最精確） |
| 2. 目錄頁偵測 | 掃描前 N 頁，正則匹配 `章節...頁碼` 模式 | 掃描版/無書籤 PDF |
| 3. 頁面取樣 | 均勻取樣 5-10 頁的開頭文字 | 無目錄的 PDF |

**關鍵正則模式：**
```python
TOC_PATTERNS = [
    r'(?:chapter|section|part|章|節|篇)\s*\d+',
    r'.{5,50}\s*\.{3,}\s*\d+',    # "標題 ...... 42" 目錄格式
    r'^\d+\.\d+\s+\w+',            # "1.1 Introduction" 編號格式
    r'^第[一二三四五六七八九十\d]+[章節篇]', # 中文章節
]
```

---

### 3.3 Range Extractor (`range_extractor.py`)

**原方案問題：**
1. Prompt 過於簡單，缺乏輸出格式約束
2. 直接 `json.loads()` 無容錯
3. 無法處理用戶直接給出明確頁範圍的情況（不需要呼叫 LLM）

**優化設計：**

```python
def extract_ranges(config: AppConfig) -> list[PageRange]:
    """
    解析自然語言描述為頁範圍。

    兩條路徑：
    1. 快速路徑：正則直接解析明確的頁範圍描述（不呼叫 LLM）
    2. LLM 路徑：透過 Claude 分析 TOC + 描述
    """
```

**PageRange 資料結構：**
```python
@dataclass
class PageRange:
    name: str           # 人類可讀名稱（用於檔名）
    start_page: int     # 起始頁（1-based, inclusive）
    end_page: int       # 結束頁（1-based, inclusive）
    reason: str         # 解析理由（debug/audit 用）
```

**快速路徑 - 正則解析：**

當描述為明確的頁範圍格式時，跳過 LLM 呼叫以節省成本：

```
支持的格式範例：
- "100-500, 501-600, 700-2200"
- "拆成四本: 100-500, 501-600, 700-2200, 2201-3000"
- "1-100 介紹, 101-500 方法論, 501-1000 案例"
```

解析正則：
```python
EXPLICIT_RANGE_PATTERN = r'(\d+)\s*[-~到至]\s*(\d+)\s*[,，;；\s]*([^,，;；\d]*)?'
```

**邏輯：** 若正則能匹配出所有範圍且頁碼合理（start < end, 不超過總頁數），直接返回結果；否則進入 LLM 路徑。

**LLM 路徑 - Prompt 設計：**

```
System: 你是 PDF 結構分析專家。嚴格輸出 JSON，不要有其他文字。

User:
## PDF 資訊
- 檔案: {filename}
- 總頁數: {total_pages}
- PDF Bookmarks: {bookmarks}
- 目錄文字: {toc_text}
- 頁面取樣: {sample_pages}

## 用戶需求
{natural_desc}

## 輸出要求
輸出 JSON 陣列，每個元素包含：
- name: string, 簡短中文名稱（用於檔名，不含特殊字元）
- start_page: integer, 起始頁碼（1-based）
- end_page: integer, 結束頁碼（1-based, inclusive）
- reason: string, 30字以內的解析理由

## 約束
- start_page 必須 >= 1
- end_page 必須 <= {total_pages}
- start_page < end_page
- 範圍之間可以不連續但不可重疊
```

**JSON 解析容錯：**
```python
def parse_llm_response(text: str) -> list[dict]:
    """
    多策略解析 LLM 回傳的 JSON：
    1. 直接 json.loads()
    2. 正則提取 ```json ... ``` 區塊
    3. 正則提取第一個 [ ... ] 區塊
    失敗則拋出明確錯誤訊息。
    """
```

**驗證規則：**
```python
def validate_ranges(ranges: list[PageRange], total_pages: int) -> list[PageRange]:
    """
    驗證並修正範圍：
    - start_page >= 1
    - end_page <= total_pages
    - start < end
    - 無重疊
    - name 去除檔名不安全字元
    驗證失敗拋出 ValueError，附帶具體問題描述。
    """
```

---

### 3.4 PDF Splitter (`pdf_splitter.py`)

**原方案問題：**
1. 混合使用 pdftk (subprocess) 和 pypdf，增加了不必要的外部依賴
2. pdftk 在部分 Linux 環境安裝困難
3. 無進度回報

**優化決策：純 pypdf 實作，移除 pdftk 依賴。**

理由：
- pypdf 對拆分操作效能足夠（不涉及渲染）
- 減少 Docker image 體積和安裝複雜度
- 3000 頁 PDF 拆分通常 < 30 秒

```python
def split_pdf(pdf_path: str, ranges: list[PageRange], output_dir: str) -> list[str]:
    """
    拆分 PDF 為多個檔案。

    Args:
        pdf_path: 來源 PDF 路徑
        ranges: 頁範圍列表
        output_dir: 輸出目錄

    Returns:
        輸出 PDF 檔案路徑列表

    流程:
        1. 一次性讀取來源 PDF (PdfReader)
        2. 逐範圍建立 PdfWriter，寫入對應頁面
        3. 驗證輸出檔案頁數是否正確
    """
```

**檔名格式：** `{序號:02d}_{name}.pdf` (例: `01_介紹.pdf`)

**進度回報：** 使用 callback 函式，CLI 層實作 tqdm 進度條。

---

### 3.5 PDF to MD Converter (`pdf_to_md.py`)

**原方案問題：**
1. marker-pdf API 已更新，`convert_single_pdf` 介面可能不同
2. 未處理 marker 安裝失敗的 fallback
3. 缺乏轉換品質控制

**雙引擎設計：**

```python
class PDFConverter:
    """PDF→MD 轉換器，支持 marker 和 pymupdf4llm 兩種引擎。"""

    def convert(self, pdf_path: str, output_md: str) -> ConvertResult:
        """
        轉換 PDF 為 Markdown。

        Returns:
            ConvertResult(
                md_path: str,
                page_count: int,
                size_bytes: int,
                converter_used: str,
                warnings: list[str]
            )
        """
```

| 引擎 | 優點 | 缺點 | 適用 |
|------|------|------|------|
| marker-pdf | 表格/公式準確度高、支持 OCR | 需要 torch、體積大、較慢 | 複雜排版、掃描件 |
| pymupdf4llm | 輕量、快速、無 GPU 依賴 | 表格處理較弱 | 純文字為主的 PDF |

**引擎選擇邏輯：**
1. 用戶透過 `--converter` 指定 → 使用指定引擎
2. 未指定 → 嘗試 marker，import 失敗則自動 fallback 到 pymupdf4llm
3. 兩者都失敗 → 報錯並提示安裝指令

---

### 3.6 MD Post-processor (`md_postprocess.py`)

**目標：** 減少 token 消耗，提升 LLM 理解效率。

```python
def postprocess_md(md_content: str, config: AppConfig) -> str:
    """
    後處理 Markdown 內容，優化 token 使用。

    處理項目（均可透過 config 開關）：
    1. 移除重複的頁首/頁尾文字
    2. 移除頁碼標記
    3. 合併連續空行為單一空行
    4. 修正斷行（移除段落內的硬換行）
    5. 標準化表格格式
    """
```

**頁首/頁尾偵測演算法：**
```
1. 將 MD 按分頁符或段落分組
2. 統計每組開頭/結尾重複出現的文字
3. 出現頻率 > 50% 的文字視為頁首/頁尾，移除
```

---

## 4. CLI Interface Design

### 4.1 Command Structure

```bash
# 基本用法
python main.py --pdf input.pdf --desc "拆成三本: 1-100, 101-500, 501-1000"

# 完整參數
python main.py \
  --pdf input.pdf \
  --desc "拆成四本: 100-500介紹, 501-600方法, 700-2200案例, 2201-3000結論" \
  --output ./output \
  --converter marker \
  --model claude-sonnet-4-20250514 \
  --toc-pages 50 \
  --no-ocr \
  --no-postprocess \
  --verbose

# 僅拆分 PDF（不轉 MD）
python main.py --pdf input.pdf --desc "1-500, 501-1000" --split-only

# 僅轉換 MD（輸入已拆分的 PDF 目錄）
python main.py --convert-dir ./pdf_chunks/ --converter pymupdf4llm

# 使用已儲存的 ranges.json（跳過 LLM 解析）
python main.py --pdf input.pdf --ranges ranges.json
```

### 4.2 CLI 參數表

| 參數 | 縮寫 | 類型 | 預設 | 說明 |
|------|------|------|------|------|
| `--pdf` | `-p` | str | (必填*) | 輸入 PDF 路徑 |
| `--desc` | `-d` | str | (必填*) | 自然語言頁範圍描述 |
| `--output` | `-o` | str | `./output` | 輸出目錄 |
| `--ranges` | `-r` | str | None | 直接使用 ranges.json，跳過 LLM |
| `--converter` | `-c` | str | `marker` | 轉換引擎: `marker` / `pymupdf4llm` |
| `--model` | `-m` | str | `claude-sonnet-4-20250514` | Claude 模型 ID |
| `--toc-pages` | | int | `30` | 目錄掃描頁數 |
| `--split-only` | | flag | False | 僅拆分，不轉 MD |
| `--convert-dir` | | str | None | 僅轉換已存在的 PDF 目錄 |
| `--no-ocr` | | flag | False | 停用 OCR |
| `--no-postprocess` | | flag | False | 停用 MD 後處理 |
| `--verbose` | `-v` | flag | False | 顯示詳細日誌 |

*使用 `--convert-dir` 時 `--pdf` 和 `--desc` 非必填。

### 4.3 Output Structure

```
output/
├── ranges.json                 # LLM 解析結果（可複用）
├── chunks/
│   ├── 01_介紹.pdf
│   ├── 02_方法.pdf
│   ├── 03_案例.pdf
│   └── 04_結論.pdf
├── markdown/
│   ├── 01_介紹.md
│   ├── 02_方法.md
│   ├── 03_案例.md
│   └── 04_結論.md
└── pipeline.log                # 執行日誌
```

---

## 5. Error Handling Strategy

### 5.1 Error Categories

| 類別 | 範例 | 處理方式 |
|------|------|---------|
| 輸入錯誤 | PDF 不存在、格式損壞 | 立即報錯退出，提示具體問題 |
| API 錯誤 | Key 無效、Rate limit、網路超時 | 重試 2 次（指數退避），失敗則報錯 |
| LLM 解析錯誤 | JSON 格式錯誤、頁碼不合理 | JSON 容錯解析 → 驗證修正 → 失敗則報錯 |
| 轉換錯誤 | marker 未安裝、某頁面轉換失敗 | 自動 fallback 引擎；單頁失敗記錄 warning 繼續 |
| 資源錯誤 | 磁碟空間不足、記憶體不足 | 報錯退出，提示所需空間 |

### 5.2 Exit Codes

| Code | 含義 |
|------|------|
| 0 | 成功 |
| 1 | 輸入參數錯誤 |
| 2 | PDF 讀取/處理錯誤 |
| 3 | LLM API 錯誤 |
| 4 | 轉換引擎錯誤 |
| 5 | 檔案系統錯誤 |

---

## 6. Dependencies

### 6.1 Core (必要)

```
pypdf>=4.0           # PDF 讀取/拆分
anthropic>=0.40      # Claude API
pydantic>=2.0        # 資料驗證 (PageRange, Config)
pyyaml>=6.0          # config.yaml 解析
tqdm>=4.60           # 進度條
```

### 6.2 Converter Engines (至少擇一)

```
# Option A: marker-pdf (推薦，高品質)
marker-pdf>=1.0

# Option B: pymupdf4llm (輕量替代)
pymupdf4llm>=0.0.10
pymupdf>=1.24
```

### 6.3 Development

```
pytest>=8.0
pytest-cov>=5.0
ruff>=0.4            # linting + formatting
```

---

## 7. Docker

### 7.1 Multi-stage Dockerfile

```dockerfile
# Stage 1: Base with system deps
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-tra tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Full (with marker, ~2GB)
FROM base AS full
COPY requirements-full.txt .
RUN pip install --no-cache-dir -r requirements-full.txt
COPY src/ /app/src/
WORKDIR /app
ENTRYPOINT ["python", "-m", "src.main"]

# Stage 3: Lite (pymupdf4llm only, ~200MB)
FROM base AS lite
COPY requirements-lite.txt .
RUN pip install --no-cache-dir -r requirements-lite.txt
COPY src/ /app/src/
WORKDIR /app
ENTRYPOINT ["python", "-m", "src.main"]
```

### 7.2 Docker Compose

```yaml
services:
  pdf-processor:
    build:
      context: .
      target: full          # 或 lite
    volumes:
      - ./input:/app/input
      - ./output:/app/output
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    command: >
      --pdf /app/input/doc.pdf
      --desc "你的描述"
      --output /app/output
```

---

## 8. Project File Structure

```
ai-split-pdf-to-md/
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI 入口 + pipeline 編排
│   ├── config.py            # AppConfig dataclass + 載入邏輯
│   ├── toc_scanner.py       # PDF 目錄/結構掃描
│   ├── range_extractor.py   # LLM 頁範圍解析 + 快速路徑
│   ├── pdf_splitter.py      # PDF 拆分 (pypdf)
│   ├── pdf_to_md.py         # PDF→MD 雙引擎轉換
│   ├── md_postprocess.py    # MD token 優化後處理
│   └── utils.py             # 共用: 檔名清理、日誌設定
├── tests/
│   ├── __init__.py
│   ├── test_range_extractor.py
│   ├── test_pdf_splitter.py
│   ├── test_md_postprocess.py
│   └── fixtures/
│       └── sample.pdf       # 測試用小 PDF
├── Dockerfile
├── docker-compose.yml
├── requirements.txt         # 完整依賴
├── requirements-full.txt    # marker 版
├── requirements-lite.txt    # pymupdf4llm 版
├── pyproject.toml           # 專案 metadata + ruff 設定
├── config.example.yaml      # 設定範例
├── SPEC.md                  # 本文件
└── README.md
```

---

## 9. Key Design Decisions

### 9.1 移除 pdftk 依賴

**原方案：** pdftk (subprocess) + pypdf 混合。

**決策：** 純 pypdf。

**理由：**
- pdftk 安裝在不同 Linux 環境經常出問題（snap/apt 版本衝突）
- 拆分操作不需要 pdftk 的進階功能（加密、表單填充）
- pypdf 拆分 3000 頁 PDF 實測 < 30 秒，效能無瓶頸
- 減少 Docker image 體積 ~50MB

### 9.2 快速路徑避免不必要的 LLM 呼叫

**原方案：** 所有描述都經過 Claude API。

**決策：** 明確格式的頁範圍直接正則解析。

**理由：**
- `"100-500, 501-600, 700-2200"` 這類描述不需要 LLM
- 省下 ~$0.01/次 API 呼叫費用和 3-5 秒延遲
- LLM 保留給真正需要語義理解的場景（如 "按章節拆分"）

### 9.3 雙引擎轉換器策略

**原方案：** 僅 marker-pdf。

**決策：** marker (主) + pymupdf4llm (備)，可切換。

**理由：**
- marker 需要 torch，Docker image 大（~2GB），部分環境不適合
- pymupdf4llm 輕量（~50MB）但品質稍差
- 提供 `--converter` 參數讓用戶根據場景選擇
- 提供 lite/full 兩種 Docker image

### 9.4 ranges.json 中間產物持久化

將 LLM 解析結果儲存為 `ranges.json`，支持 `--ranges` 參數直接載入。

**理由：**
- 避免重複 LLM 呼叫（同一 PDF 重新處理時）
- 方便手動微調頁範圍後重跑 pipeline
- 提供可審計的解析記錄

---

## 10. Pipeline Execution Flow

```
main(pdf, desc, output)
│
├─ 1. Load config (CLI args + env + yaml)
│
├─ 2. Validate input
│     ├─ PDF exists and readable
│     ├─ Output dir writable
│     └─ API key present (if LLM needed)
│
├─ 3. Extract ranges
│     ├─ Try regex fast path
│     │   └─ Success? → skip LLM
│     └─ LLM path
│         ├─ scan_toc(pdf) → toc_info
│         ├─ call Claude API(toc_info + desc)
│         ├─ parse JSON response (3-layer fallback)
│         └─ validate ranges
│     └─ Save ranges.json
│
├─ 4. Split PDF (if not --convert-dir mode)
│     ├─ PdfReader(pdf) once
│     ├─ For each range: PdfWriter → write pages → save
│     └─ Verify page counts
│
├─ 5. Convert to MD (if not --split-only)
│     ├─ For each chunk PDF:
│     │   ├─ converter.convert(pdf) → raw MD
│     │   └─ postprocess(raw MD) → optimized MD
│     └─ Save to markdown/ dir
│
└─ 6. Summary report
      ├─ Total time
      ├─ Files created
      ├─ Size comparison (PDF vs MD)
      └─ Token estimate (chars / 4)
```

---

## 11. Testing Strategy

### 11.1 Unit Tests

| 模組 | 測試重點 |
|------|---------|
| `range_extractor` | 正則快速路徑各格式、JSON 容錯解析、驗證邏輯 |
| `toc_scanner` | 書籤提取、目錄頁偵測、正則模式匹配 |
| `pdf_splitter` | 頁數正確性、邊界條件（單頁、最後一頁） |
| `md_postprocess` | 頁首頁尾移除、空行合併、斷行修正 |
| `config` | 優先順序、環境變數覆蓋、型別驗證 |

### 11.2 Integration Tests

- 完整 pipeline: 小型 PDF → ranges → chunks → MD
- `--split-only` 模式
- `--convert-dir` 模式
- `--ranges` 載入模式

### 11.3 Mock 策略

- Claude API: mock `anthropic.Anthropic.messages.create`，回傳預設 JSON
- PDF 轉換: 使用 `tests/fixtures/sample.pdf`（10 頁小 PDF）

---

## 12. Performance Expectations

| 操作 | 1000 頁 PDF | 3000 頁 PDF |
|------|------------|------------|
| TOC 掃描 | < 3s | < 5s |
| LLM 解析 | 3-8s | 3-8s (不受頁數影響) |
| PDF 拆分 | < 10s | < 30s |
| MD 轉換 (marker) | 5-15 min | 15-45 min |
| MD 轉換 (pymupdf4llm) | 1-3 min | 3-10 min |
| 後處理 | < 5s | < 15s |

---

## 13. Development Phases

### Phase 1: Core Pipeline (MVP)

- [ ] `config.py` - AppConfig + CLI argparse
- [ ] `toc_scanner.py` - PDF 結構掃描
- [ ] `range_extractor.py` - 快速路徑 + LLM 解析
- [ ] `pdf_splitter.py` - pypdf 拆分
- [ ] `main.py` - Pipeline 編排 (split-only 模式)
- [ ] 基礎 unit tests

**驗收標準：** `python main.py --pdf test.pdf --desc "1-100, 101-200" --split-only` 正確拆分。

### Phase 2: MD Conversion

- [ ] `pdf_to_md.py` - 雙引擎轉換
- [ ] `md_postprocess.py` - Token 優化
- [ ] 完整 pipeline 整合
- [ ] Integration tests

**驗收標準：** 完整 pipeline 產出結構化 MD，token 量比原始 PDF 文字減少 30%+。

### Phase 3: Docker + Polish

- [ ] Dockerfile (multi-stage)
- [ ] docker-compose.yml
- [ ] README.md
- [ ] config.example.yaml
- [ ] CI lint + test

**驗收標準：** `docker compose up` 一鍵執行完整 pipeline。
