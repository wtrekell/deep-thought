"""Tests for the shared text utilities in deep_thought.text_utils."""

from __future__ import annotations

import pytest

from deep_thought.text_utils import slugify


class TestSlugify:
    """Tests for the shared slugify() function."""

    def test_lowercases_input(self) -> None:
        """Uppercase letters must be converted to lowercase."""
        assert slugify("HelloWorld") == "helloworld"

    def test_replaces_spaces_with_hyphens(self) -> None:
        """Spaces must be replaced with hyphens."""
        assert slugify("hello world") == "hello-world"

    def test_removes_special_characters(self) -> None:
        """Non-alphanumeric characters must be replaced with hyphens."""
        assert slugify("hello! world?") == "hello-world"

    def test_collapses_consecutive_non_alnum_runs_to_single_hyphen(self) -> None:
        """A run of multiple non-alphanumeric characters must become one hyphen."""
        assert slugify("hello   world") == "hello-world"

    def test_strips_leading_hyphens(self) -> None:
        """Leading hyphens must be stripped from the result."""
        assert slugify("--hello") == "hello"

    def test_strips_trailing_hyphens(self) -> None:
        """Trailing hyphens must be stripped from the result."""
        assert slugify("hello--") == "hello"

    def test_strips_both_leading_and_trailing_hyphens(self) -> None:
        """Both leading and trailing hyphens must be removed."""
        assert slugify("--hello-world--") == "hello-world"

    def test_empty_string_returns_empty(self) -> None:
        """An empty string input must return an empty string by default."""
        assert slugify("") == ""

    def test_empty_fallback_returned_for_empty_result(self) -> None:
        """When the slug reduces to empty, empty_fallback must be returned."""
        assert slugify("", empty_fallback="no-title") == "no-title"
        assert slugify("!@#$", empty_fallback="no-title") == "no-title"

    def test_empty_fallback_not_returned_for_non_empty_result(self) -> None:
        """empty_fallback must not be returned when the slug is non-empty."""
        assert slugify("hello", empty_fallback="no-title") == "hello"

    def test_strips_trailing_hyphen_at_truncation_boundary(self) -> None:
        """A trailing hyphen introduced at the truncation boundary must be stripped."""
        # 79 'a' chars + '!' + more chars — naive truncation at 80 leaves a trailing hyphen.
        text = "a" * 79 + "!" + "b" * 10
        result = slugify(text, max_length=80)
        assert not result.endswith("-")
        assert len(result) <= 80

    def test_already_valid_slug_is_unchanged(self) -> None:
        """A string that is already a valid slug must pass through unchanged."""
        assert slugify("my-slug-123") == "my-slug-123"

    def test_default_max_length_is_80(self) -> None:
        """The default max_length must be 80 characters."""
        long_input = "a" * 200
        result = slugify(long_input)
        assert len(result) == 80

    def test_custom_max_length_is_respected(self) -> None:
        """A caller-specified max_length must cap the result at that length."""
        long_input = "a" * 200
        result = slugify(long_input, max_length=100)
        assert len(result) == 100

    def test_result_never_exceeds_max_length(self) -> None:
        """The result must never be longer than max_length regardless of input."""
        for max_len in (10, 50, 80, 100):
            result = slugify("x" * 300, max_length=max_len)
            assert len(result) <= max_len

    def test_path_traversal_string_is_sanitised(self) -> None:
        """A path traversal attempt must not produce dots or slashes in the slug."""
        result = slugify("../../evil")
        assert "/" not in result
        assert ".." not in result

    @pytest.mark.parametrize(
        "raw_input, expected_slug",
        [
            ("My Blog Post", "my-blog-post"),
            ("What is Python async?", "what-is-python-async"),
            ("C++ vs Rust: performance", "c-vs-rust-performance"),
            ("Hello, World!", "hello-world"),
            ("  leading and trailing  ", "leading-and-trailing"),
        ],
    )
    def test_parametrized_common_inputs(self, raw_input: str, expected_slug: str) -> None:
        """Common realistic inputs must produce the expected slug."""
        assert slugify(raw_input) == expected_slug
