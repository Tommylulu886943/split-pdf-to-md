import os
import pytest

from src.config import load_config, validate_config, AppConfig


class TestLoadConfig:
    def test_basic_args(self):
        config = load_config(["--pdf", "test.pdf", "--desc", "1-100"])
        assert config.pdf_path == "test.pdf"
        assert config.natural_desc == "1-100"

    def test_defaults(self):
        config = load_config(["--pdf", "test.pdf", "--desc", "x"])
        assert config.output_dir == "./output"
        assert config.split_only is False
        assert config.verbose is False

    def test_all_flags(self):
        config = load_config([
            "--pdf", "test.pdf",
            "--desc", "1-100",
            "--output", "/tmp/out",
            "--model", "claude-opus-4-20250514",
            "--toc-pages", "50",
            "--split-only",
            "--verbose",
        ])
        assert config.output_dir == "/tmp/out"
        assert config.model == "claude-opus-4-20250514"
        assert config.toc_scan_pages == 50
        assert config.split_only is True
        assert config.verbose is True

    def test_ranges_file(self):
        config = load_config(["--pdf", "test.pdf", "--ranges", "ranges.json"])
        assert config.ranges_file == "ranges.json"

    def test_convert_dir(self):
        config = load_config(["--convert-dir", "/tmp/pdfs"])
        assert config.convert_dir == "/tmp/pdfs"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        config = load_config(["--pdf", "test.pdf", "--desc", "x"])
        assert config.anthropic_api_key == "test-key-123"


class TestValidateConfig:
    def test_valid_config(self, sample_pdf):
        config = AppConfig(pdf_path=sample_pdf, natural_desc="1-5")
        errors = validate_config(config)
        assert errors == []

    def test_missing_pdf(self):
        config = AppConfig(pdf_path="", natural_desc="1-5")
        errors = validate_config(config)
        assert any("--pdf" in e for e in errors)

    def test_pdf_not_found(self):
        config = AppConfig(pdf_path="/nonexistent.pdf", natural_desc="1-5")
        errors = validate_config(config)
        assert any("not found" in e for e in errors)

    def test_missing_desc_and_ranges(self, sample_pdf):
        config = AppConfig(pdf_path=sample_pdf)
        errors = validate_config(config)
        assert any("--desc or --ranges" in e for e in errors)

    def test_ranges_file_ok(self, sample_pdf, tmp_path):
        ranges_file = tmp_path / "ranges.json"
        ranges_file.write_text("[]")
        config = AppConfig(pdf_path=sample_pdf, ranges_file=str(ranges_file))
        errors = validate_config(config)
        assert errors == []

    def test_convert_dir_mode(self, tmp_path):
        config = AppConfig(convert_dir=str(tmp_path))
        errors = validate_config(config)
        assert errors == []

    def test_convert_dir_not_found(self):
        config = AppConfig(convert_dir="/nonexistent")
        errors = validate_config(config)
        assert any("not found" in e for e in errors)
