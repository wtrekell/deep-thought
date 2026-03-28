"""Tests for the HTML-to-markdown converter in deep_thought.web.converter."""

from __future__ import annotations

from pathlib import Path

from deep_thought.web.converter import apply_boilerplate_patterns, convert_html_to_markdown, count_words, extract_title

# ---------------------------------------------------------------------------
# TestConvertHtmlToMarkdown
# ---------------------------------------------------------------------------


class TestConvertHtmlToMarkdown:
    def test_h1_converts_to_markdown_heading(self) -> None:
        """An HTML <h1> tag must be converted to a '# heading' in markdown."""
        html_content = "<h1>My Heading</h1>"
        result = convert_html_to_markdown(html_content)
        assert "# My Heading" in result

    def test_paragraph_converts_to_plain_text(self) -> None:
        """An HTML <p> tag must produce plain text without HTML tags."""
        html_content = "<p>Hello world, this is a test paragraph.</p>"
        result = convert_html_to_markdown(html_content)
        assert "Hello world, this is a test paragraph." in result
        assert "<p>" not in result
        assert "</p>" not in result

    def test_empty_string_returns_empty_or_whitespace(self) -> None:
        """An empty HTML input must return an empty string or only whitespace."""
        result = convert_html_to_markdown("")
        assert result.strip() == ""

    def test_images_are_ignored(self) -> None:
        """Image tags must not produce any output (ignore_images=True)."""
        html_content = '<p>Text</p><img src="/photo.jpg" alt="A photo">'
        result = convert_html_to_markdown(html_content)
        assert "photo.jpg" not in result
        assert "![" not in result

    def test_links_are_preserved(self) -> None:
        """Anchor tags must be preserved as markdown links."""
        html_content = '<a href="https://example.com">Click here</a>'
        result = convert_html_to_markdown(html_content)
        assert "Click here" in result
        assert "https://example.com" in result

    def test_result_is_stripped(self) -> None:
        """The returned string must not have leading or trailing whitespace."""
        html_content = "<p>Some text.</p>"
        result = convert_html_to_markdown(html_content)
        assert result == result.strip()

    def test_article_fixture_produces_heading_and_paragraph(self) -> None:
        """Converting the article fixture must yield a heading and paragraph text."""
        fixture_path = Path(__file__).parent / "fixtures" / "article.html"
        html_content = fixture_path.read_text(encoding="utf-8")
        result = convert_html_to_markdown(html_content)
        assert "# Post One" in result
        assert "content of post one" in result


# ---------------------------------------------------------------------------
# TestCountWords
# ---------------------------------------------------------------------------


class TestCountWords:
    def test_counts_words_in_simple_sentence(self) -> None:
        """count_words must return the correct word count for a simple sentence."""
        assert count_words("Hello world this is text") == 5

    def test_empty_string_returns_zero(self) -> None:
        """count_words on an empty string must return 0."""
        assert count_words("") == 0

    def test_extra_whitespace_does_not_inflate_count(self) -> None:
        """Multiple spaces between words must not increase the word count."""
        assert count_words("  word   another  ") == 2

    def test_newlines_treated_as_word_separators(self) -> None:
        """Newlines must be treated as word separators, not inflate the count."""
        assert count_words("line one\nline two") == 4

    def test_single_word_returns_one(self) -> None:
        """A string containing only one word must return 1."""
        assert count_words("hello") == 1


# ---------------------------------------------------------------------------
# TestExtractTitle
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_returns_title_from_title_tag(self) -> None:
        """extract_title must return the text content of a <title> tag."""
        html_content = "<html><head><title>My Page Title</title></head></html>"
        assert extract_title(html_content) == "My Page Title"

    def test_returns_none_when_no_title_tag(self) -> None:
        """extract_title must return None when no <title> tag is present."""
        html_content = "<html><head></head><body><p>No title here.</p></body></html>"
        assert extract_title(html_content) is None

    def test_returns_none_for_empty_html(self) -> None:
        """extract_title must return None for an empty HTML string."""
        assert extract_title("") is None

    def test_strips_whitespace_from_title(self) -> None:
        """The returned title must have surrounding whitespace stripped."""
        html_content = "<title>  Padded Title  </title>"
        result = extract_title(html_content)
        assert result == "Padded Title"

    def test_article_fixture_title(self) -> None:
        """extract_title on the article fixture must return the expected title."""
        fixture_path = Path(__file__).parent / "fixtures" / "article.html"
        html_content = fixture_path.read_text(encoding="utf-8")
        result = extract_title(html_content)
        assert result == "Post One - My Blog"

    def test_blog_index_fixture_title(self) -> None:
        """extract_title on the blog_index fixture must return 'My Blog'."""
        fixture_path = Path(__file__).parent / "fixtures" / "blog_index.html"
        html_content = fixture_path.read_text(encoding="utf-8")
        result = extract_title(html_content)
        assert result == "My Blog"


# ---------------------------------------------------------------------------
# TestApplyBoilerplatePatterns
# ---------------------------------------------------------------------------


class TestApplyBoilerplatePatterns:
    def test_empty_patterns_returns_text_unchanged(self) -> None:
        """An empty pattern list must return the input text exactly as-is."""
        original_text = "# Title\n\nSome article content here."
        result = apply_boilerplate_patterns(original_text, [])
        assert result == original_text

    def test_single_pattern_removes_matching_text(self) -> None:
        """A single pattern must remove all matching occurrences."""
        text = "# Title\n\nArticle content.\n\nSubscribe to our newsletter today!"
        patterns = [r"Subscribe to our newsletter.*"]
        result = apply_boilerplate_patterns(text, patterns)
        assert "Subscribe" not in result
        assert "Article content." in result

    def test_multiple_patterns_applied_in_order(self) -> None:
        """All patterns in the list must be applied, removing each match."""
        text = "NAV: Home | About\n\n# Title\n\nContent here.\n\nFooter: Copyright 2026"
        patterns = [r"NAV:[^\n]*\n", r"Footer:[^\n]*"]
        result = apply_boilerplate_patterns(text, patterns)
        assert "NAV" not in result
        assert "Footer" not in result
        assert "Content here." in result

    def test_multiline_pattern_removal(self) -> None:
        """Patterns with re.DOTALL must match across multiple lines."""
        text = "# Title\n\nGood content.\n\nRelated Posts\n- Post A\n- Post B\n\nMore content."
        patterns = [r"Related Posts.*?(?=\n\n|\Z)"]
        result = apply_boilerplate_patterns(text, patterns)
        assert "Related Posts" not in result
        assert "Post A" not in result
        assert "Good content." in result
        assert "More content." in result

    def test_whitespace_normalized_after_removal(self) -> None:
        """Runs of three or more newlines after removal must collapse to double newlines."""
        text = "Intro.\n\n\n\n\nBoilerplate block.\n\n\n\n\nConclusion."
        patterns = [r"Boilerplate block\."]
        result = apply_boilerplate_patterns(text, patterns)
        assert "\n\n\n" not in result
        assert "Intro." in result
        assert "Conclusion." in result

    def test_no_match_returns_text_unchanged(self) -> None:
        """A pattern that matches nothing must leave the text unchanged."""
        original_text = "# Title\n\nJust article content."
        patterns = [r"NONEXISTENT_BOILERPLATE"]
        result = apply_boilerplate_patterns(original_text, patterns)
        assert result == original_text
