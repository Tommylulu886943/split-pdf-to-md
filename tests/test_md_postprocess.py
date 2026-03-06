import pytest

from src.md_postprocess import (
    postprocess_md,
    PostprocessConfig,
    _remove_repeated_headers_footers,
    _remove_page_numbers,
    _fix_broken_lines,
    _normalize_whitespace,
)


class TestRemovePageNumbers:
    def test_standalone_number(self):
        text = "Some text\n42\nMore text"
        result = _remove_page_numbers(text)
        assert "42" not in result
        assert "Some text" in result

    def test_dash_format(self):
        text = "Content\n- 15 -\nMore"
        result = _remove_page_numbers(text)
        assert "- 15 -" not in result

    def test_page_keyword(self):
        text = "Content\nPage 7\nMore"
        result = _remove_page_numbers(text)
        assert "Page 7" not in result

    def test_p_dot_format(self):
        text = "Content\np. 123\nMore"
        result = _remove_page_numbers(text)
        assert "p. 123" not in result

    def test_preserves_long_lines_with_numbers(self):
        text = "This line has 42 in it and is long enough"
        result = _remove_page_numbers(text)
        assert "42" in result

    def test_preserves_numbers_in_context(self):
        text = "There are 100 items in this list"
        result = _remove_page_numbers(text)
        assert "100" in result


class TestRemoveHeadersFooters:
    def test_repeated_header(self):
        segments = []
        for i in range(6):
            segments.append(f"CONFIDENTIAL DOCUMENT\n\nContent of section {i}\n\nPage footer")
        content = "\n---\n".join(segments)
        result = _remove_repeated_headers_footers(content)
        assert "CONFIDENTIAL DOCUMENT" not in result
        assert "Content of section 3" in result

    def test_no_removal_with_few_segments(self):
        content = "Header\n\nContent\n---\nHeader\n\nMore content"
        result = _remove_repeated_headers_footers(content)
        assert "Header" in result  # too few segments to detect

    def test_preserves_unique_lines(self):
        segments = []
        for i in range(6):
            segments.append(f"REPEATED\n\nUnique content {i}\n\nAlso unique {i * 10}")
        content = "\n---\n".join(segments)
        result = _remove_repeated_headers_footers(content)
        assert "Unique content 3" in result


class TestFixBrokenLines:
    def test_join_mid_sentence(self):
        text = "This is a long sentence that was\nbroken across two lines."
        result = _fix_broken_lines(text)
        assert "that was broken across" in result

    def test_preserve_headings(self):
        text = "Some text\n# Heading"
        result = _fix_broken_lines(text)
        assert "\n# Heading" in result

    def test_preserve_list_items(self):
        text = "Intro text\n- Item one\n- Item two"
        result = _fix_broken_lines(text)
        assert "\n- Item one" in result
        assert "\n- Item two" in result

    def test_preserve_blank_lines(self):
        text = "Paragraph one.\n\nParagraph two."
        result = _fix_broken_lines(text)
        assert "\n\n" in result

    def test_no_join_after_period(self):
        text = "End of sentence.\nStart of new one."
        result = _fix_broken_lines(text)
        assert "\n" in result
        assert "sentence. Start" not in result

    def test_preserve_table_rows(self):
        text = "| col1 | col2 |\n| val1 | val2 |"
        result = _fix_broken_lines(text)
        assert "\n" in result

    def test_join_with_paren(self):
        text = "The method\n(described above) works well"
        result = _fix_broken_lines(text)
        assert "method (described" in result


class TestNormalizeWhitespace:
    def test_collapse_blank_lines(self):
        text = "Line 1\n\n\n\n\nLine 2"
        result = _normalize_whitespace(text)
        assert result == "Line 1\n\nLine 2\n"

    def test_trim_trailing_spaces(self):
        text = "Line with trailing   \nAnother line  "
        result = _normalize_whitespace(text)
        assert "   \n" not in result
        assert "  " not in result or result.endswith("\n")

    def test_preserves_single_blank_line(self):
        text = "Para 1\n\nPara 2"
        result = _normalize_whitespace(text)
        assert result == "Para 1\n\nPara 2\n"


class TestPostprocessIntegration:
    def test_full_pipeline(self):
        content = (
            "HEADER TEXT\n\n"
            "Some interesting content that was\n"
            "broken across lines for no reason.\n\n"
            "42\n\n"
            "---\n\n"
            "HEADER TEXT\n\n"
            "More content in the second\n"
            "section of the document.\n\n"
            "43\n\n"
            "---\n\n"
            "HEADER TEXT\n\n"
            "Third section with some\n"
            "additional material here.\n\n"
            "44\n\n"
            "---\n\n"
            "HEADER TEXT\n\n"
            "Fourth section continues\n"
            "the discussion further.\n\n"
            "45\n"
        )
        result = postprocess_md(content)
        # Page numbers removed
        assert "\n42\n" not in result
        # Broken lines joined
        assert "content that was broken" in result
        # No excessive blank lines
        assert "\n\n\n" not in result

    def test_all_disabled(self):
        config = PostprocessConfig(
            remove_headers_footers=False,
            remove_page_numbers=False,
            normalize_whitespace=False,
            fix_broken_lines=False,
        )
        content = "  Some text  \n\n\n\n42\n"
        result = postprocess_md(content, config)
        assert result == content  # unchanged
