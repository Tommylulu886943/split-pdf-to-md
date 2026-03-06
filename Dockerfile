##############################################
# Stage: base - shared system dependencies
##############################################
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-tra \
    tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./

##############################################
# Stage: lite - pymupdf4llm only (~250MB)
##############################################
FROM base AS lite

COPY requirements-lite.txt .
RUN pip install --no-cache-dir -r requirements-lite.txt

COPY src/ ./src/

ENTRYPOINT ["python", "-m", "src.main"]

##############################################
# Stage: full - marker-pdf + pymupdf4llm (~2.5GB)
##############################################
FROM base AS full

COPY requirements-full.txt .
RUN pip install --no-cache-dir -r requirements-full.txt

COPY src/ ./src/

ENTRYPOINT ["python", "-m", "src.main"]
