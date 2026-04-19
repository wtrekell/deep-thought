"""Tests for the URL filtering and link extraction functions in deep_thought.web.filters."""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_thought.web.filters import (
    canonicalize_url,
    extract_internal_links,
    has_markdown_link_corruption,
    is_same_domain,
    is_url_allowed,
    matches_any_pattern,
)

# ---------------------------------------------------------------------------
# TestMatchesAnyPattern
# ---------------------------------------------------------------------------


class TestMatchesAnyPattern:
    def test_returns_true_when_url_matches_a_pattern(self) -> None:
        """matches_any_pattern must return True when at least one pattern matches."""
        url = "https://example.com/blog/post-one"
        patterns = [r"/blog/", r"/docs/"]
        assert matches_any_pattern(url, patterns) is True

    def test_returns_false_when_no_patterns_match(self) -> None:
        """matches_any_pattern must return False when no pattern matches the URL."""
        url = "https://example.com/about"
        patterns = [r"/blog/", r"/docs/"]
        assert matches_any_pattern(url, patterns) is False

    def test_empty_patterns_list_returns_false(self) -> None:
        """An empty patterns list must always return False."""
        assert matches_any_pattern("https://example.com/anything", []) is False

    def test_pattern_uses_regex_search_not_full_match(self) -> None:
        """Patterns are matched with regex search, so partial matches count."""
        url = "https://example.com/blog/post-one"
        patterns = [r"post"]
        assert matches_any_pattern(url, patterns) is True

    def test_returns_true_on_first_matching_pattern(self) -> None:
        """If the first pattern matches, the function returns True without checking others."""
        url = "https://example.com/blog"
        patterns = [r"/blog", r"/this-should-never-run"]
        assert matches_any_pattern(url, patterns) is True


# ---------------------------------------------------------------------------
# TestIsUrlAllowed
# ---------------------------------------------------------------------------


class TestIsUrlAllowed:
    def test_no_include_no_exclude_returns_true(self) -> None:
        """With no include or exclude patterns, every URL is allowed."""
        assert is_url_allowed("https://example.com/page", [], []) is True

    def test_url_matching_include_pattern_is_allowed(self) -> None:
        """A URL that matches an include pattern must be allowed (no excludes)."""
        url = "https://example.com/blog/post"
        assert is_url_allowed(url, [r"/blog/"], []) is True

    def test_url_not_matching_include_pattern_is_rejected(self) -> None:
        """A URL that does not match any include pattern must be rejected."""
        url = "https://example.com/about"
        assert is_url_allowed(url, [r"/blog/"], []) is False

    def test_url_matching_exclude_pattern_is_rejected(self) -> None:
        """A URL that matches an exclude pattern must be rejected."""
        url = "https://example.com/login"
        assert is_url_allowed(url, [], [r"login"]) is False

    def test_exclude_wins_over_include(self) -> None:
        """When a URL matches both include and exclude patterns, exclude wins."""
        url = "https://example.com/blog/login"
        include_patterns = [r"/blog/"]
        exclude_patterns = [r"login"]
        assert is_url_allowed(url, include_patterns, exclude_patterns) is False

    def test_url_matching_include_but_not_exclude_is_allowed(self) -> None:
        """A URL matching include but not exclude must be allowed."""
        url = "https://example.com/blog/post"
        include_patterns = [r"/blog/"]
        exclude_patterns = [r"login"]
        assert is_url_allowed(url, include_patterns, exclude_patterns) is True


# ---------------------------------------------------------------------------
# TestIsSameDomain
# ---------------------------------------------------------------------------


class TestIsSameDomain:
    def test_same_domain_returns_true(self) -> None:
        """Two URLs with the same domain must return True."""
        assert is_same_domain("https://example.com/page", "https://example.com/") is True

    def test_different_domain_returns_false(self) -> None:
        """Two URLs with different domains must return False."""
        assert is_same_domain("https://other.com/page", "https://example.com/") is False

    def test_www_and_non_www_are_treated_as_same_domain(self) -> None:
        """www.example.com and example.com must be treated as the same domain."""
        assert is_same_domain("https://www.example.com/page", "https://example.com/") is True

    def test_non_www_and_www_root_are_same_domain(self) -> None:
        """example.com and www.example.com (as root) must be treated as the same domain."""
        assert is_same_domain("https://example.com/page", "https://www.example.com/") is True

    def test_subdomain_is_different_from_root_domain(self) -> None:
        """A subdomain like blog.example.com must not match example.com."""
        assert is_same_domain("https://blog.example.com/post", "https://example.com/") is False

    @pytest.mark.error_handling
    def test_url_with_no_domain_does_not_crash(self) -> None:
        """A relative or malformed URL must not raise an exception."""
        result = is_same_domain("/relative/path", "https://example.com/")
        assert result is False


# ---------------------------------------------------------------------------
# TestExtractInternalLinks
# ---------------------------------------------------------------------------


class TestExtractInternalLinks:
    def test_returns_only_same_domain_links(self) -> None:
        """extract_internal_links must return only links sharing the root domain."""
        fixture_path = Path(__file__).parent / "fixtures" / "blog_index.html"
        html_content = fixture_path.read_text(encoding="utf-8")
        root_url = "https://myblog.com/"

        result = extract_internal_links(html_content, root_url)

        # External link to external.com must not be included
        assert not any("external.com" in url for url in result)

    def test_resolves_relative_urls_to_absolute(self) -> None:
        """Relative href values must be resolved against the root URL."""
        html_content = '<a href="/blog/post-one">Post One</a>'
        root_url = "https://myblog.com/"

        result = extract_internal_links(html_content, root_url)

        assert "https://myblog.com/blog/post-one" in result

    def test_results_are_sorted_and_deduplicated(self) -> None:
        """Results must be deduplicated and sorted for deterministic ordering."""
        html_content = """
            <a href="/page-b">B</a>
            <a href="/page-a">A</a>
            <a href="/page-b">B again</a>
        """
        root_url = "https://example.com/"

        result = extract_internal_links(html_content, root_url)

        assert result == sorted(set(result))
        assert len(result) == 2

    def test_fragment_is_stripped_from_links(self) -> None:
        """Fragment identifiers (#section) must be stripped from extracted links."""
        html_content = '<a href="/page#section-two">Section Two</a>'
        root_url = "https://example.com/"

        result = extract_internal_links(html_content, root_url)

        assert "https://example.com/page" in result
        assert not any("#" in url for url in result)

    def test_empty_html_returns_empty_list(self) -> None:
        """Empty HTML input must return an empty list."""
        result = extract_internal_links("", "https://example.com/")
        assert result == []

    def test_html_with_no_links_returns_empty_list(self) -> None:
        """HTML with no anchor tags must return an empty list."""
        html_content = "<p>No links here.</p>"
        result = extract_internal_links(html_content, "https://example.com/")
        assert result == []

    def test_docs_root_fixture_returns_only_internal_links(self) -> None:
        """The docs_root fixture must return only the two /docs/ internal links."""
        fixture_path = Path(__file__).parent / "fixtures" / "docs_root.html"
        html_content = fixture_path.read_text(encoding="utf-8")
        root_url = "https://docs.example.com/"

        result = extract_internal_links(html_content, root_url)

        assert not any("github.com" in url for url in result)
        assert len(result) == 2

    def test_canonicalizes_trailing_slash_duplicates(self) -> None:
        """Links differing only by trailing slash must collapse to a single canonical entry."""
        html_content = """
            <a href="/foo">no slash</a>
            <a href="/foo/">trailing slash</a>
        """
        root_url = "https://example.com/"

        result = extract_internal_links(html_content, root_url)

        assert result == ["https://example.com/foo"]

    def test_canonicalizes_www_and_apex_duplicates(self) -> None:
        """Links to www and apex variants of the same host must collapse."""
        html_content = """
            <a href="https://www.example.com/page">www variant</a>
            <a href="https://example.com/page">apex variant</a>
        """
        root_url = "https://example.com/"

        result = extract_internal_links(html_content, root_url)

        assert result == ["https://example.com/page"]

    def test_drops_links_with_markdown_link_corruption(self) -> None:
        """Links whose path contains raw or encoded markdown-link brackets must be dropped."""
        html_content = """
            <a href="/components/accordion/%5Bhttps:/example.com/guide%5D(https:/example.com/guide)">broken</a>
            <a href="/components/checkbox/code">clean</a>
        """
        root_url = "https://example.com/"

        result = extract_internal_links(html_content, root_url)

        assert result == ["https://example.com/components/checkbox/code"]


# ---------------------------------------------------------------------------
# TestCanonicalizeUrl
# ---------------------------------------------------------------------------


class TestCanonicalizeUrl:
    def test_strips_trailing_slash_from_non_root_path(self) -> None:
        """A trailing slash on a non-root path must be stripped."""
        assert canonicalize_url("https://example.com/foo/") == "https://example.com/foo"

    def test_preserves_root_slash(self) -> None:
        """The single trailing slash on a root URL must be preserved."""
        assert canonicalize_url("https://example.com/") == "https://example.com/"

    def test_folds_www_to_apex(self) -> None:
        """A leading www. on the netloc must fold to the apex domain."""
        assert canonicalize_url("https://www.example.com/foo") == "https://example.com/foo"

    def test_lowercases_scheme_and_netloc(self) -> None:
        """Scheme and netloc must be lowercased per RFC 3986."""
        assert canonicalize_url("HTTPS://Example.COM/foo") == "https://example.com/foo"

    def test_preserves_query_string(self) -> None:
        """Query strings must not be altered — they can be semantically significant."""
        assert canonicalize_url("https://example.com/foo?x=1") == "https://example.com/foo?x=1"

    def test_preserves_path_case(self) -> None:
        """Path case must not change."""
        assert canonicalize_url("https://example.com/Foo/Bar") == "https://example.com/Foo/Bar"

    def test_idempotent(self) -> None:
        """Canonicalizing an already-canonical URL must return the same string."""
        once = canonicalize_url("https://www.example.com/Foo/")
        twice = canonicalize_url(once)
        assert once == twice


# ---------------------------------------------------------------------------
# TestHasMarkdownLinkCorruption
# ---------------------------------------------------------------------------


class TestHasMarkdownLinkCorruption:
    def test_returns_false_for_clean_url(self) -> None:
        """A normal URL must not be flagged."""
        assert has_markdown_link_corruption("https://example.com/foo/bar") is False

    def test_detects_percent_encoded_bracket(self) -> None:
        """A %5B or %5D anywhere in path or query must be flagged."""
        assert has_markdown_link_corruption("https://example.com/x/%5Bhttps:/y%5D(z)") is True

    def test_detects_lowercase_percent_encoded_bracket(self) -> None:
        """Lowercase %5b / %5d must also be flagged."""
        assert has_markdown_link_corruption("https://example.com/x/%5bhttps:/y%5d(z)") is True

    def test_detects_literal_brackets(self) -> None:
        """Raw square brackets in the path must be flagged."""
        assert has_markdown_link_corruption("https://example.com/x/[y](z)") is True

    def test_query_only_bracket_is_flagged(self) -> None:
        """Brackets appearing only in the query string must still be flagged."""
        assert has_markdown_link_corruption("https://example.com/x?ref=%5Bhttps:/y%5D") is True
