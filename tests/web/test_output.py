"""Tests for the page output writer in deep_thought.web.output."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from deep_thought.web.output import slugify, url_to_output_path, write_page

# ---------------------------------------------------------------------------
# TestSlugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_converts_spaces_to_hyphens(self) -> None:
        """Spaces in the input text must be replaced with hyphens."""
        assert slugify("hello world") == "hello-world"

    def test_lowercases_input(self) -> None:
        """Uppercase letters must be converted to lowercase."""
        assert slugify("MyPageTitle") == "mypagetitle"

    def test_removes_special_characters(self) -> None:
        """Non-alphanumeric characters other than hyphens must be removed."""
        assert slugify("hello! world?") == "hello-world"

    def test_collapses_multiple_hyphens(self) -> None:
        """Consecutive hyphens must be collapsed into a single hyphen."""
        assert slugify("hello---world") == "hello-world"

    def test_strips_leading_and_trailing_hyphens(self) -> None:
        """Leading and trailing hyphens must be removed from the result."""
        assert slugify("--hello-world--") == "hello-world"

    def test_truncates_to_100_characters(self) -> None:
        """The result must be at most 100 characters long."""
        long_text = "a" * 200
        result = slugify(long_text)
        assert len(result) <= 100

    def test_empty_string_returns_empty(self) -> None:
        """An empty string input must return an empty string."""
        assert slugify("") == ""

    def test_url_path_segment_preserved(self) -> None:
        """A URL-safe slug (lowercase alphanumeric and hyphens) is returned unchanged."""
        assert slugify("my-blog-post") == "my-blog-post"


# ---------------------------------------------------------------------------
# TestUrlToOutputPath
# ---------------------------------------------------------------------------


class TestUrlToOutputPath:
    def test_simple_url_returns_correct_path_structure(self, tmp_path: Path) -> None:
        """A URL with a single path segment must map to domain/segment.md."""
        url = "https://example.com/about"
        output_path = url_to_output_path(url, tmp_path)
        assert output_path == tmp_path / "example.com" / "about.md"

    def test_url_with_nested_path_creates_subdirectories(self, tmp_path: Path) -> None:
        """A URL with nested path segments must map to domain/dir/segment.md."""
        url = "https://example.com/blog/my-post"
        output_path = url_to_output_path(url, tmp_path)
        assert output_path == tmp_path / "example.com" / "blog" / "my-post.md"

    def test_url_with_no_path_returns_index_md(self, tmp_path: Path) -> None:
        """A URL with no path (root only) must use 'index.md' as the filename."""
        url = "https://example.com/"
        output_path = url_to_output_path(url, tmp_path)
        assert output_path == tmp_path / "example.com" / "index.md"

    def test_url_with_bare_domain_returns_index_md(self, tmp_path: Path) -> None:
        """A URL with just a domain and no trailing slash must use 'index.md'."""
        url = "https://example.com"
        output_path = url_to_output_path(url, tmp_path)
        assert output_path == tmp_path / "example.com" / "index.md"

    def test_output_path_has_md_extension(self, tmp_path: Path) -> None:
        """The output path must always end with the .md extension."""
        url = "https://example.com/page"
        output_path = url_to_output_path(url, tmp_path)
        assert output_path.suffix == ".md"

    def test_slugifies_last_path_segment(self, tmp_path: Path) -> None:
        """The last path segment must be slugified to form the filename."""
        url = "https://example.com/My Page Title"
        output_path = url_to_output_path(url, tmp_path)
        assert "my-page-title" in output_path.name or output_path.name == "my-page-title.md"

    def test_strip_path_prefix_removes_prefix(self, tmp_path: Path) -> None:
        """A matching prefix must be stripped from the URL path."""
        url = "https://code.claude.com/docs/en/overview"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="/docs/en")
        assert output_path == tmp_path / "code.claude.com" / "overview.md"

    def test_strip_path_prefix_preserves_hierarchy_below_prefix(self, tmp_path: Path) -> None:
        """Path segments after the stripped prefix must be preserved."""
        url = "https://code.claude.com/docs/en/guides/setup"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="/docs/en")
        assert output_path == tmp_path / "code.claude.com" / "guides" / "setup.md"

    def test_strip_path_prefix_no_match_passes_through(self, tmp_path: Path) -> None:
        """When the URL path does not start with the prefix, no stripping occurs."""
        url = "https://example.com/other/page"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="/docs/en")
        assert output_path == tmp_path / "example.com" / "other" / "page.md"

    def test_strip_path_prefix_none_is_noop(self, tmp_path: Path) -> None:
        """When strip_path_prefix is None, the output path is unchanged."""
        url = "https://example.com/docs/en/overview"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix=None)
        assert output_path == tmp_path / "example.com" / "docs" / "en" / "overview.md"

    def test_strip_path_prefix_exact_match_returns_index(self, tmp_path: Path) -> None:
        """When the entire URL path equals the prefix, the result must be index.md."""
        url = "https://example.com/docs/en"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="/docs/en")
        assert output_path == tmp_path / "example.com" / "index.md"

    def test_strip_path_prefix_partial_segment_no_strip(self, tmp_path: Path) -> None:
        """A prefix that partially matches a segment must NOT be stripped."""
        url = "https://example.com/docs/english/page"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="/docs/en")
        assert output_path == tmp_path / "example.com" / "docs" / "english" / "page.md"

    def test_strip_path_prefix_trailing_slash_normalized(self, tmp_path: Path) -> None:
        """A prefix with a trailing slash must work the same as without."""
        url = "https://code.claude.com/docs/en/overview"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="/docs/en/")
        assert output_path == tmp_path / "code.claude.com" / "overview.md"

    def test_strip_path_prefix_without_leading_slash(self, tmp_path: Path) -> None:
        """A prefix without a leading slash must work the same as with one."""
        url = "https://code.claude.com/docs/en/overview"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="docs/en")
        assert output_path == tmp_path / "code.claude.com" / "overview.md"

    def test_strip_domain_omits_domain_directory(self, tmp_path: Path) -> None:
        """When strip_domain is True, the domain directory must be omitted."""
        url = "https://example.com/blog/my-post"
        output_path = url_to_output_path(url, tmp_path, strip_domain=True)
        assert output_path == tmp_path / "blog" / "my-post.md"

    def test_strip_domain_false_includes_domain(self, tmp_path: Path) -> None:
        """When strip_domain is False, the domain directory must be present."""
        url = "https://example.com/blog/my-post"
        output_path = url_to_output_path(url, tmp_path, strip_domain=False)
        assert output_path == tmp_path / "example.com" / "blog" / "my-post.md"

    def test_strip_domain_root_url_returns_index(self, tmp_path: Path) -> None:
        """A root URL with strip_domain must produce index.md directly in output_root."""
        url = "https://example.com/"
        output_path = url_to_output_path(url, tmp_path, strip_domain=True)
        assert output_path == tmp_path / "index.md"

    def test_strip_domain_combined_with_strip_path_prefix(self, tmp_path: Path) -> None:
        """strip_domain and strip_path_prefix must work together."""
        url = "https://code.claude.com/docs/en/overview"
        output_path = url_to_output_path(url, tmp_path, strip_path_prefix="/docs/en", strip_domain=True)
        assert output_path == tmp_path / "overview.md"

    def test_strip_domain_preserves_path_hierarchy(self, tmp_path: Path) -> None:
        """With strip_domain, path segments must still form subdirectories."""
        url = "https://example.com/guides/setup/install"
        output_path = url_to_output_path(url, tmp_path, strip_domain=True)
        assert output_path == tmp_path / "guides" / "setup" / "install.md"


# ---------------------------------------------------------------------------
# TestWritePage
# ---------------------------------------------------------------------------


class TestWritePage:
    def test_creates_file_at_correct_path(self, output_root: Path) -> None:
        """write_page must create a file at the URL-derived output path."""
        url = "https://example.com/blog/post-one"
        result_path = write_page(
            markdown_text="# Post One\n\nSome content.",
            url=url,
            mode="blog",
            title="Post One",
            word_count=4,
            output_root=output_root,
        )
        assert result_path.exists()
        assert result_path == output_root / "example.com" / "blog" / "post-one.md"

    def test_file_contains_yaml_frontmatter(self, output_root: Path) -> None:
        """The written file must start with a valid YAML frontmatter block."""
        url = "https://example.com/about"
        write_page(
            markdown_text="About content.",
            url=url,
            mode="blog",
            title="About",
            word_count=2,
            output_root=output_root,
        )
        output_path = output_root / "example.com" / "about.md"
        file_content = output_path.read_text(encoding="utf-8")
        assert file_content.startswith("---\n")

    def test_frontmatter_includes_tool_web(self, output_root: Path) -> None:
        """The frontmatter must include 'tool: web' to identify the source tool."""
        url = "https://example.com/page"
        result_path = write_page(
            markdown_text="Page content.",
            url=url,
            mode="documentation",
            title="Page",
            word_count=2,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        assert "tool: web" in file_content

    def test_frontmatter_includes_source_url(self, output_root: Path) -> None:
        """The frontmatter must include the source URL of the crawled page."""
        url = "https://example.com/my-page"
        result_path = write_page(
            markdown_text="Content here.",
            url=url,
            mode="blog",
            title="My Page",
            word_count=2,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        assert f"url: {url}" in file_content

    def test_frontmatter_includes_mode(self, output_root: Path) -> None:
        """The frontmatter must include the crawl mode used."""
        url = "https://example.com/docs/guide"
        result_path = write_page(
            markdown_text="Guide content.",
            url=url,
            mode="documentation",
            title="Guide",
            word_count=2,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        assert "mode: documentation" in file_content

    def test_frontmatter_includes_word_count(self, output_root: Path) -> None:
        """The frontmatter must include the word count of the page content."""
        url = "https://example.com/article"
        result_path = write_page(
            markdown_text="Hello world.",
            url=url,
            mode="blog",
            title="Article",
            word_count=42,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        assert "word_count: 42" in file_content

    def test_title_is_included_when_provided(self, output_root: Path) -> None:
        """When a title is given, it must appear in the frontmatter."""
        url = "https://example.com/titled-page"
        result_path = write_page(
            markdown_text="Content.",
            url=url,
            mode="blog",
            title="My Title",
            word_count=1,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        assert 'title: "My Title"' in file_content

    def test_title_is_omitted_when_none(self, output_root: Path) -> None:
        """When title is None, no 'title:' field must appear in the frontmatter."""
        url = "https://example.com/untitled"
        result_path = write_page(
            markdown_text="Content.",
            url=url,
            mode="blog",
            title=None,
            word_count=1,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        assert "title:" not in file_content

    def test_markdown_body_follows_frontmatter(self, output_root: Path) -> None:
        """The markdown body must appear after the closing '---' of frontmatter."""
        url = "https://example.com/body-test"
        body_text = "# Title\n\nBody paragraph here."
        result_path = write_page(
            markdown_text=body_text,
            url=url,
            mode="blog",
            title="Body Test",
            word_count=5,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        # Find closing --- and verify body appears after it
        opening_end = file_content.index("\n---\n", 4) + 5  # skip past closing ---
        body_portion = file_content[opening_end:]
        assert "# Title" in body_portion

    def test_creates_parent_directories(self, output_root: Path) -> None:
        """write_page must create any missing parent directories automatically."""
        url = "https://example.com/a/b/c/deep-page"
        result_path = write_page(
            markdown_text="Deep content.",
            url=url,
            mode="blog",
            title=None,
            word_count=2,
            output_root=output_root,
        )
        assert result_path.exists()

    def test_returns_path_to_written_file(self, output_root: Path) -> None:
        """write_page must return the Path to the file that was created."""
        url = "https://example.com/return-check"
        returned_path = write_page(
            markdown_text="Content.",
            url=url,
            mode="direct",
            title=None,
            word_count=1,
            output_root=output_root,
        )
        assert returned_path.is_file()

    @pytest.mark.error_handling
    def test_output_file_is_utf8_encoded(self, output_root: Path) -> None:
        """The written file must be UTF-8 encoded and handle Unicode content."""
        url = "https://example.com/unicode-page"
        markdown_content = "# Héllo Wörld\n\nUnicode: \u4e2d\u6587"
        result_path = write_page(
            markdown_text=markdown_content,
            url=url,
            mode="blog",
            title="Unicode Page",
            word_count=3,
            output_root=output_root,
        )
        file_content = result_path.read_text(encoding="utf-8")
        assert "Héllo Wörld" in file_content
