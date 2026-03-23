"""Tests for the Gmail Tool newsletter HTML cleaner."""

from __future__ import annotations

from deep_thought.gmail.cleaner import (
    _remove_script_tags,
    _remove_style_tags,
    _remove_tracking_pixels,
    clean_newsletter_html,
)


class TestRemoveTrackingPixels:
    """Tests for _remove_tracking_pixels."""

    def test_removes_1x1_image(self) -> None:
        """Should remove img tags with width=1 height=1."""
        html = '<p>Hello</p><img width="1" height="1" src="https://track.example.com/pixel.gif"/><p>World</p>'
        result = _remove_tracking_pixels(html)
        assert "track.example.com" not in result
        assert "<p>Hello</p>" in result

    def test_removes_tracking_src(self) -> None:
        """Should remove img tags with tracking-related src URLs."""
        html = '<img src="https://example.com/track/open?id=123" />'
        result = _remove_tracking_pixels(html)
        assert "<img" not in result

    def test_preserves_normal_images(self) -> None:
        """Should keep regular images that are not tracking pixels."""
        html = '<img src="https://example.com/photo.jpg" width="600" height="400"/>'
        result = _remove_tracking_pixels(html)
        assert "photo.jpg" in result


class TestRemoveScriptTags:
    """Tests for _remove_script_tags."""

    def test_removes_scripts(self) -> None:
        """Should remove script tags and their content."""
        html = "<p>Content</p><script>alert('xss')</script><p>More</p>"
        result = _remove_script_tags(html)
        assert "<script" not in result
        assert "alert" not in result
        assert "<p>Content</p>" in result


class TestRemoveStyleTags:
    """Tests for _remove_style_tags."""

    def test_removes_styles(self) -> None:
        """Should remove style tags and their content."""
        html = "<style>.red { color: red; }</style><p>Content</p>"
        result = _remove_style_tags(html)
        assert "<style" not in result
        assert "<p>Content</p>" in result


class TestCleanNewsletterHtml:
    """Tests for the main clean_newsletter_html function."""

    def test_converts_to_markdown(self) -> None:
        """Should convert cleaned HTML to markdown text."""
        html = "<h1>Weekly Digest</h1><p>This is the main content.</p>"
        result = clean_newsletter_html(html)
        assert "Weekly Digest" in result
        assert "main content" in result

    def test_strips_all_non_content(self) -> None:
        """Should remove scripts, styles, and tracking in one pass."""
        html = (
            "<style>.x{}</style>"
            "<script>track()</script>"
            '<img width="1" height="1" src="https://track.example.com/px"/>'
            "<h1>Title</h1>"
            "<p>Real content here.</p>"
        )
        result = clean_newsletter_html(html)
        assert "Title" in result
        assert "Real content" in result
        assert "<script" not in result
        assert "<style" not in result
        assert "track.example.com" not in result

    def test_handles_empty_html(self) -> None:
        """Should return empty string for empty input."""
        assert clean_newsletter_html("") == ""

    def test_handles_malformed_html(self) -> None:
        """Should not crash on malformed HTML."""
        html = "<p>Unclosed <b>tags <i>everywhere"
        result = clean_newsletter_html(html)
        assert "Unclosed" in result

    def test_preserves_links(self) -> None:
        """Should keep hyperlinks in the output."""
        html = '<p>Visit <a href="https://example.com">our site</a></p>'
        result = clean_newsletter_html(html)
        assert "example.com" in result
