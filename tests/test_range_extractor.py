import json
import pytest

from src.range_extractor import (
    _try_fast_path,
    _parse_json_response,
    _validate_ranges,
    PageRange,
    save_ranges,
    load_ranges,
)


class TestFastPath:
    def test_simple_ranges(self):
        result = _try_fast_path("1-100, 101-200, 201-300", total_pages=300)
        assert result is not None
        assert len(result) == 3
        assert result[0].start_page == 1
        assert result[0].end_page == 100
        assert result[2].end_page == 300

    def test_ranges_with_labels(self):
        result = _try_fast_path("1-100 intro, 101-500 methods", total_pages=500)
        assert result is not None
        assert len(result) == 2
        assert result[0].name == "intro"
        assert result[1].name == "methods"

    def test_chinese_separator(self):
        result = _try_fast_path("1-100，101-200", total_pages=200)
        assert result is not None
        assert len(result) == 2

    def test_tilde_separator(self):
        result = _try_fast_path("1~100, 101~200", total_pages=200)
        assert result is not None
        assert len(result) == 2

    def test_chinese_range_word(self):
        result = _try_fast_path("1到100, 101至200", total_pages=200)
        assert result is not None
        assert len(result) == 2

    def test_exceeds_total_pages(self):
        result = _try_fast_path("1-100, 101-500", total_pages=200)
        assert result is None  # falls through to LLM

    def test_overlapping_ranges(self):
        result = _try_fast_path("1-150, 100-200", total_pages=200)
        assert result is None

    def test_invalid_range_start_gt_end(self):
        result = _try_fast_path("200-100", total_pages=300)
        assert result is None

    def test_no_match(self):
        result = _try_fast_path("split by chapters please", total_pages=100)
        assert result is None

    def test_prefix_text_with_ranges(self):
        result = _try_fast_path("Split into: 1-50, 51-100", total_pages=100)
        assert result is not None
        assert len(result) == 2

    def test_auto_naming(self):
        result = _try_fast_path("1-50, 51-100", total_pages=100)
        assert result is not None
        assert result[0].name == "part_1"
        assert result[1].name == "part_2"


class TestParseJsonResponse:
    def test_direct_json(self):
        data = [{"name": "ch1", "start_page": 1, "end_page": 50, "reason": "test"}]
        result = _parse_json_response(json.dumps(data))
        assert len(result) == 1
        assert result[0]["name"] == "ch1"

    def test_json_with_code_fence(self):
        text = '```json\n[{"name": "a", "start_page": 1, "end_page": 10}]\n```'
        result = _parse_json_response(text)
        assert len(result) == 1

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n[{"name": "a", "start_page": 1, "end_page": 10}]\nDone.'
        result = _parse_json_response(text)
        assert len(result) == 1

    def test_unparseable(self):
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _parse_json_response("This is not JSON at all")


class TestValidateRanges:
    def test_valid_ranges(self):
        ranges = [
            PageRange("a", 1, 50),
            PageRange("b", 51, 100),
        ]
        result = _validate_ranges(ranges, total_pages=100)
        assert len(result) == 2

    def test_clamp_start_page(self):
        ranges = [PageRange("a", 0, 50)]
        result = _validate_ranges(ranges, total_pages=100)
        assert result[0].start_page == 1

    def test_clamp_end_page(self):
        ranges = [PageRange("a", 1, 200)]
        result = _validate_ranges(ranges, total_pages=100)
        assert result[0].end_page == 100

    def test_reject_invalid_range(self):
        ranges = [PageRange("a", 50, 50)]
        with pytest.raises(ValueError, match="start.*>= end"):
            _validate_ranges(ranges, total_pages=100)

    def test_reject_overlap(self):
        ranges = [
            PageRange("a", 1, 60),
            PageRange("b", 50, 100),
        ]
        with pytest.raises(ValueError, match="Overlapping"):
            _validate_ranges(ranges, total_pages=100)

    def test_empty_ranges(self):
        with pytest.raises(ValueError, match="No page ranges"):
            _validate_ranges([], total_pages=100)

    def test_sanitize_name(self):
        ranges = [PageRange("bad/name:here", 1, 50)]
        result = _validate_ranges(ranges, total_pages=100)
        assert "/" not in result[0].name
        assert ":" not in result[0].name


class TestSaveLoadRanges:
    def test_roundtrip(self, tmp_path):
        ranges = [
            PageRange("intro", 1, 50, "test"),
            PageRange("body", 51, 100, "test"),
        ]
        path = str(tmp_path / "ranges.json")
        save_ranges(ranges, path)
        loaded = load_ranges(path)
        assert len(loaded) == 2
        assert loaded[0].name == "intro"
        assert loaded[1].end_page == 100
