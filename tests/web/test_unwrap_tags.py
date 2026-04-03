"""Tests for the unwrap_tags feature in the web tool.

Covers:
- unwrap_html_tags() in deep_thought.web.converter
- unwrap_tags config field parsing in deep_thought.web.config._parse_crawl_config
"""

from __future__ import annotations

import pytest

from deep_thought.web.config import _parse_crawl_config, validate_config
from deep_thought.web.converter import unwrap_html_tags

# ---------------------------------------------------------------------------
# TestUnwrapHtmlTags — converter function
# ---------------------------------------------------------------------------


class TestUnwrapHtmlTags:
    """Tests for unwrap_html_tags() in deep_thought.web.converter."""

    # ------------------------------------------------------------------
    # Basic functionality
    # ------------------------------------------------------------------

    def test_empty_pattern_list_returns_html_unchanged(self) -> None:
        """An empty tag_patterns list must return the input HTML exactly as-is."""
        html_input = "<p>Hello <div class='word'>world</div></p>"
        result = unwrap_html_tags(html_input, [])
        assert result == html_input

    def test_single_tag_class_pattern_strips_wrapper_keeps_content(self) -> None:
        """A single tag.class pattern must remove the wrapper tag but keep its text."""
        html_input = '<p><div class="word">Hello</div> <div class="word">world</div></p>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "Hello" in result
        assert "world" in result
        assert "<div" not in result
        assert "</div>" not in result

    def test_multiple_patterns_are_all_applied(self) -> None:
        """All patterns in the list must be applied to the HTML."""
        html_input = '<p><span class="char">H</span><div class="word">ello</div> world</p>'
        result = unwrap_html_tags(html_input, ["div.word", "span.char"])
        assert "H" in result
        assert "ello" in result
        assert " world" in result
        assert "<div" not in result
        assert "<span" not in result

    def test_no_matching_tags_returns_html_unchanged(self) -> None:
        """HTML with no tags matching the pattern must be returned unchanged."""
        html_input = "<p>Hello <strong>world</strong></p>"
        result = unwrap_html_tags(html_input, ["div.word"])
        assert result == html_input

    def test_empty_html_string_returns_empty(self) -> None:
        """An empty HTML string must return an empty string regardless of patterns."""
        result = unwrap_html_tags("", ["div.word"])
        assert result == ""

    # ------------------------------------------------------------------
    # Tag-only pattern (no class)
    # ------------------------------------------------------------------

    def test_tag_without_class_unwraps_all_instances(self) -> None:
        """A pattern with just a tag name (no .class) must unwrap all matching tags."""
        html_input = "<p><span>first</span> and <span>second</span></p>"
        result = unwrap_html_tags(html_input, ["span"])
        assert "first" in result
        assert "second" in result
        assert "<span" not in result
        assert "</span>" not in result

    def test_tag_without_class_preserves_non_matching_tags(self) -> None:
        """A tag-only pattern must not affect other tag types."""
        html_input = "<p><span>text</span> and <em>emphasis</em></p>"
        result = unwrap_html_tags(html_input, ["span"])
        assert "<em>emphasis</em>" in result

    # ------------------------------------------------------------------
    # Class matching precision
    # ------------------------------------------------------------------

    def test_class_match_is_whole_word(self) -> None:
        """A class pattern must not match a tag whose class is only a substring match.

        'div.word' must not strip <div class="password"> because 'word' is not
        a standalone class token in 'password'.
        """
        html_input = '<div class="password">secret</div>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert result == html_input

    def test_class_match_works_with_multiple_classes_on_tag(self) -> None:
        """The target class is matched even when the tag has additional classes."""
        html_input = '<div class="word animate fade">Hello</div>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "Hello" in result
        assert "<div" not in result

    def test_wrong_class_name_leaves_tag_intact(self) -> None:
        """A tag whose class does not match the pattern must be left in place."""
        html_input = '<div class="sentence">Full sentence here.</div>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert result == html_input

    def test_wrong_tag_name_leaves_tag_intact(self) -> None:
        """A matching class on the wrong tag type must not be unwrapped."""
        html_input = '<span class="word">Hello</span>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert result == html_input

    def test_data_class_attribute_is_not_matched(self) -> None:
        """A data-class attribute whose value matches the pattern must not be unwrapped.

        'div.word' must not strip <div data-class="word"> because the tag has no
        actual class="word" attribute.  The hyphen in "data-class" creates a word
        boundary that a \\b-based regex would incorrectly treat as a match point.
        """
        html_input = '<div data-class="word">Hello</div>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert result == html_input

    # ------------------------------------------------------------------
    # Nested content
    # ------------------------------------------------------------------

    def test_inline_html_inside_wrapper_is_preserved(self) -> None:
        """Inline HTML nested inside a matched wrapper tag must be preserved."""
        html_input = '<div class="word"><strong>bold</strong></div>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "<strong>bold</strong>" in result

    def test_realistic_word_animation_html(self) -> None:
        """Realistic word-animation HTML (like claude.com/blog) must be fully unwrapped."""
        html_input = (
            "<p>"
            '<div class="word" aria-hidden="true">The</div> '
            '<div class="word" aria-hidden="true">quick</div> '
            '<div class="word" aria-hidden="true">brown</div>'
            "</p>"
        )
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "The" in result
        assert "quick" in result
        assert "brown" in result
        assert "<div" not in result

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_pattern_with_extra_dot_splits_on_first_dot_only(self) -> None:
        """A pattern like 'div.foo.bar' must use 'foo.bar' as the class name (split on first dot only)."""
        # The implementation does pattern.split(".", 1) so "div.foo.bar" → tag="div", class="foo.bar"
        # A tag whose class is "foo" (not "foo.bar") must NOT be matched
        html_input = '<div class="foo">text</div>'
        result = unwrap_html_tags(html_input, ["div.foo.bar"])
        assert result == html_input

    # ------------------------------------------------------------------
    # Case insensitivity
    # ------------------------------------------------------------------

    def test_case_insensitive_tag_name(self) -> None:
        """Uppercase tag names in HTML must be matched by lowercase patterns."""
        html_input = '<DIV class="word">Hello</DIV>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "Hello" in result
        assert "<DIV" not in result

    def test_case_insensitive_mixed_case_tag(self) -> None:
        """Mixed-case tag names must also be matched."""
        html_input = '<Div class="word">Hello</Div>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "Hello" in result
        assert "<Div" not in result

    # ------------------------------------------------------------------
    # Single-quote support
    # ------------------------------------------------------------------

    def test_single_quoted_class_attribute(self) -> None:
        """Tags with single-quoted class values must be matched."""
        html_input = "<div class='word'>Hello</div>"
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "Hello" in result
        assert "<div" not in result

    # ------------------------------------------------------------------
    # Whitespace normalization
    # ------------------------------------------------------------------

    def test_excess_newlines_collapsed_after_unwrapping(self) -> None:
        """Three or more consecutive newlines must be collapsed to two after unwrapping."""
        html_input = '<div class="word">Hello</div>\n\n\n\n<div class="word">world</div>'
        result = unwrap_html_tags(html_input, ["div.word"])
        assert "\n\n\n" not in result
        assert "Hello\n\nworld" in result

    # ------------------------------------------------------------------
    # Parametrized matching matrix
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "pattern, html_input, should_unwrap",
        [
            ("div.word", '<div class="word">text</div>', True),
            ("div.word", '<div class="sentence">text</div>', False),
            ("span.char", '<span class="char">x</span>', True),
            ("span.char", '<div class="char">x</div>', False),
            ("p", "<p>paragraph text</p>", True),
        ],
    )
    def test_pattern_matching_matrix(self, pattern: str, html_input: str, should_unwrap: bool) -> None:
        """Parametrized checks that patterns correctly match or skip various tag/class combos."""
        result = unwrap_html_tags(html_input, [pattern])
        tag_still_present = f"<{pattern.split('.')[0]}" in result
        if should_unwrap:
            assert not tag_still_present, f"Pattern '{pattern}' should have unwrapped: {html_input}"
        else:
            assert result == html_input, f"Pattern '{pattern}' should not have changed: {html_input}"


# ---------------------------------------------------------------------------
# TestParseUnwrapTagsConfig — config parsing
# ---------------------------------------------------------------------------


class TestParseUnwrapTagsConfig:
    """Tests for unwrap_tags field parsing inside _parse_crawl_config."""

    def _minimal_raw_config(self) -> dict[str, object]:
        """Return a minimal raw config dict that satisfies all required fields."""
        return {
            "mode": "blog",
            "output_dir": "output/web/",
        }

    def test_unwrap_tags_parsed_from_list(self) -> None:
        """unwrap_tags must be parsed correctly when provided as a YAML list."""
        raw = self._minimal_raw_config()
        raw["unwrap_tags"] = ["div.word", "span.char"]
        config = _parse_crawl_config(raw)
        assert config.unwrap_tags == ["div.word", "span.char"]

    def test_unwrap_tags_defaults_to_empty_list_when_absent(self) -> None:
        """unwrap_tags must default to an empty list when the key is not in the config."""
        raw = self._minimal_raw_config()
        config = _parse_crawl_config(raw)
        assert config.unwrap_tags == []

    def test_unwrap_tags_defaults_to_empty_list_when_none(self) -> None:
        """unwrap_tags must default to an empty list when the value is None (null in YAML)."""
        raw = self._minimal_raw_config()
        raw["unwrap_tags"] = None
        config = _parse_crawl_config(raw)
        assert config.unwrap_tags == []

    def test_unwrap_tags_single_item_list(self) -> None:
        """A single-item list must be parsed as a list with one element."""
        raw = self._minimal_raw_config()
        raw["unwrap_tags"] = ["div.word"]
        config = _parse_crawl_config(raw)
        assert config.unwrap_tags == ["div.word"]

    def test_unwrap_tags_empty_list_in_config(self) -> None:
        """An explicit empty list must be stored as an empty list (not None)."""
        raw = self._minimal_raw_config()
        raw["unwrap_tags"] = []
        config = _parse_crawl_config(raw)
        assert config.unwrap_tags == []
        assert isinstance(config.unwrap_tags, list)

    def test_unwrap_tags_non_list_value_defaults_to_empty_list(self) -> None:
        """A non-list value (e.g. a plain string) must be ignored and default to empty list."""
        raw = self._minimal_raw_config()
        raw["unwrap_tags"] = "div.word"
        config = _parse_crawl_config(raw)
        assert config.unwrap_tags == []

    def test_unwrap_tags_coexists_with_strip_boilerplate(self) -> None:
        """Both unwrap_tags and strip_boilerplate must be parsed independently."""
        raw = self._minimal_raw_config()
        raw["unwrap_tags"] = ["div.word"]
        raw["strip_boilerplate"] = [r"Related Posts.*"]
        config = _parse_crawl_config(raw)
        assert config.unwrap_tags == ["div.word"]
        assert config.strip_boilerplate == [r"Related Posts.*"]


# ---------------------------------------------------------------------------
# TestValidateUnwrapTags — config validation
# ---------------------------------------------------------------------------


class TestValidateUnwrapTags:
    """Tests for unwrap_tags validation in validate_config()."""

    def _make_config_with_unwrap_tags(self, patterns: list[str]) -> object:
        """Build a minimal WebConfig with the given unwrap_tags patterns."""
        raw_crawl = {
            "mode": "blog",
            "output_dir": "output/web/",
            "unwrap_tags": patterns,
        }
        from deep_thought.web.config import WebConfig

        crawl = _parse_crawl_config(raw_crawl)
        return WebConfig(crawl=crawl)

    def test_valid_patterns_produce_no_issues(self) -> None:
        """Well-formed patterns must pass validation with no issues."""
        config = self._make_config_with_unwrap_tags(["div.word", "span.char", "p"])
        issues = validate_config(config)
        assert not any("unwrap_tags" in issue for issue in issues)

    def test_empty_tag_name_produces_issue(self) -> None:
        """A pattern like '.word' (missing tag name) must be flagged."""
        config = self._make_config_with_unwrap_tags([".word"])
        issues = validate_config(config)
        assert any("missing tag name" in issue for issue in issues)

    def test_invalid_tag_name_produces_issue(self) -> None:
        """A pattern with a non-HTML tag name must be flagged."""
        config = self._make_config_with_unwrap_tags(["123.word"])
        issues = validate_config(config)
        assert any("invalid HTML tag name" in issue for issue in issues)
