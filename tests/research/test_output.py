"""Tests for the Research Tool markdown output generation."""

from __future__ import annotations

from pathlib import Path

import yaml

from deep_thought.research.models import ResearchResult, SearchResult
from deep_thought.research.output import (
    _build_frontmatter,
    _escape_markdown,
    _escape_yaml_value,
    generate_research_markdown,
    write_research_file,
)
from deep_thought.text_utils import slugify as _slugify

# ---------------------------------------------------------------------------
# Helper to create a test ResearchResult
# ---------------------------------------------------------------------------


def _make_result(**overrides: object) -> ResearchResult:
    """Return a ResearchResult with sensible defaults, optionally overridden."""
    defaults: dict[str, object] = {
        "query": "What is MLX?",
        "mode": "search",
        "model": "sonar",
        "recency": None,
        "domains": [],
        "context_files": [],
        "answer": "MLX is Apple's machine learning framework for Apple Silicon.",
        "search_results": [],
        "related_questions": [],
        "cost_usd": 0.0065,
        "processed_date": "2026-03-23T12:00:00Z",
    }
    defaults.update(overrides)
    return ResearchResult(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestSlugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Tests for the shared slugify function as used by the research tool."""

    def test_normal_text(self) -> None:
        """Should lowercase and replace spaces with hyphens."""
        assert _slugify("Hello World") == "hello-world"

    def test_special_characters(self) -> None:
        """Should replace non-alphanumeric characters with a single hyphen."""
        assert _slugify("Test! @#$ Event") == "test-event"

    def test_empty_string_with_no_title_fallback(self) -> None:
        """Should return 'no-title' when empty_fallback is provided."""
        assert _slugify("", empty_fallback="no-title") == "no-title"

    def test_truncation(self) -> None:
        """Should truncate the slug to the specified max_length."""
        long_text = "a" * 100
        result = _slugify(long_text, max_length=80)
        assert len(result) <= 80

    def test_only_special_chars_with_no_title_fallback(self) -> None:
        """Should return 'no-title' when input contains only special characters."""
        assert _slugify("!@#$", empty_fallback="no-title") == "no-title"

    def test_strips_trailing_hyphen_after_truncation(self) -> None:
        """Should strip a trailing hyphen that appears at the truncation boundary."""
        # Build a string that places a special char exactly at position max_length
        # so that naive truncation would leave a trailing hyphen.
        text = "a" * 79 + "!" + "b" * 10
        result = _slugify(text, max_length=80)
        assert not result.endswith("-")
        assert len(result) <= 80


# ---------------------------------------------------------------------------
# TestEscapeYamlValue
# ---------------------------------------------------------------------------


class TestEscapeYamlValue:
    """Tests for _escape_yaml_value."""

    def test_escapes_backslash(self) -> None:
        """Should replace a backslash with two backslashes."""
        assert _escape_yaml_value("path\\to\\file") == "path\\\\to\\\\file"

    def test_escapes_double_quote(self) -> None:
        """Should replace a double quote with a backslash-escaped double quote."""
        assert _escape_yaml_value('say "hello"') == 'say \\"hello\\"'

    def test_escapes_combined(self) -> None:
        """Should handle a string containing both backslashes and double quotes."""
        assert _escape_yaml_value('C:\\Users\\"name"') == 'C:\\\\Users\\\\\\"name\\"'


# ---------------------------------------------------------------------------
# TestEscapeMarkdown
# ---------------------------------------------------------------------------


class TestEscapeMarkdown:
    """Tests for _escape_markdown."""

    def test_escapes_square_brackets(self) -> None:
        """Should escape opening and closing square brackets."""
        assert _escape_markdown("[link text]") == r"\[link text\]"

    def test_escapes_asterisks(self) -> None:
        """Should escape asterisks used for bold or italic markup."""
        assert _escape_markdown("**bold**") == r"\*\*bold\*\*"

    def test_escapes_underscores(self) -> None:
        """Should escape underscores used for italic markup."""
        assert _escape_markdown("_italic_") == r"\_italic\_"

    def test_escapes_backticks(self) -> None:
        """Should escape backticks used for inline code."""
        assert _escape_markdown("`code`") == r"\`code\`"

    def test_plain_text_unchanged(self) -> None:
        """Should leave plain text with no special characters unchanged."""
        assert _escape_markdown("plain text") == "plain text"

    def test_mixed_special_chars(self) -> None:
        """Should escape all special characters in a mixed string."""
        result = _escape_markdown("[title] with *emphasis*")
        assert result == r"\[title\] with \*emphasis\*"


# ---------------------------------------------------------------------------
# TestBuildFrontmatter
# ---------------------------------------------------------------------------


class TestBuildFrontmatter:
    """Tests for _build_frontmatter."""

    def test_includes_required_fields(self) -> None:
        """Should always include tool, query, mode, model, cost_usd, and processed_date."""
        result = _make_result()
        frontmatter = _build_frontmatter(result)
        assert "tool: research" in frontmatter
        assert 'query: "What is MLX?"' in frontmatter
        assert "mode: search" in frontmatter
        assert "model: sonar" in frontmatter
        assert "cost_usd:" in frontmatter
        assert "processed_date:" in frontmatter

    def test_omits_none_recency(self) -> None:
        """Should not include a recency line when recency is None."""
        result = _make_result(recency=None)
        frontmatter = _build_frontmatter(result)
        assert "recency:" not in frontmatter

    def test_includes_recency_when_set(self) -> None:
        """Should include recency when it holds a non-None value."""
        result = _make_result(recency="month")
        frontmatter = _build_frontmatter(result)
        assert "recency: month" in frontmatter

    def test_omits_empty_domains(self) -> None:
        """Should not include a domains section when the list is empty."""
        result = _make_result(domains=[])
        frontmatter = _build_frontmatter(result)
        assert "domains:" not in frontmatter

    def test_includes_domains_when_present(self) -> None:
        """Should render a YAML list under domains when entries exist."""
        result = _make_result(domains=["example.com", "docs.python.org"])
        frontmatter = _build_frontmatter(result)
        assert "domains:" in frontmatter
        assert '  - "example.com"' in frontmatter
        assert '  - "docs.python.org"' in frontmatter

    def test_omits_empty_context_files(self) -> None:
        """Should not include a context_files section when the list is empty."""
        result = _make_result(context_files=[])
        frontmatter = _build_frontmatter(result)
        assert "context_files:" not in frontmatter

    def test_includes_context_files_when_present(self) -> None:
        """Should render a quoted YAML list under context_files when entries exist."""
        result = _make_result(context_files=["/home/user/notes.md"])
        frontmatter = _build_frontmatter(result)
        assert "context_files:" in frontmatter
        assert '  - "/home/user/notes.md"' in frontmatter

    def test_escapes_query_with_special_chars(self) -> None:
        """Should escape double quotes inside the query value."""
        result = _make_result(query='What is "MLX"?')
        frontmatter = _build_frontmatter(result)
        assert '\\"MLX\\"' in frontmatter

    def test_cost_formatted_with_precision(self) -> None:
        """Should format cost_usd to six decimal places with trailing zeros stripped."""
        result = _make_result(cost_usd=0.006)
        frontmatter = _build_frontmatter(result)
        assert "cost_usd: 0.006" in frontmatter

    def test_cost_strips_floating_point_noise(self) -> None:
        """Should strip floating-point noise (e.g. 0.006000000000000001 → 0.006)."""
        result = _make_result(cost_usd=0.006000000000000001)
        frontmatter = _build_frontmatter(result)
        # The noisy float should be normalised to exactly six decimal places then stripped.
        assert "cost_usd: 0.006" in frontmatter
        assert "0.006000000000000001" not in frontmatter

    def test_yaml_roundtrip(self) -> None:
        """Generated frontmatter should be syntactically valid YAML with correct field values."""
        result = _make_result(
            query="What is MLX?",
            mode="search",
            model="sonar",
            cost_usd=0.0065,
            processed_date="2026-03-23T12:00:00Z",
            recency="month",
            domains=["example.com"],
        )
        frontmatter_block = _build_frontmatter(result)

        # Strip the opening and closing '---' delimiters and parse the YAML body.
        lines = frontmatter_block.split("\n")
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)

        assert parsed["tool"] == "research"
        assert parsed["query"] == "What is MLX?"
        assert parsed["mode"] == "search"
        assert parsed["model"] == "sonar"
        assert parsed["recency"] == "month"
        assert isinstance(parsed["cost_usd"], float)
        # YAML parses the ISO-8601 timestamp as a datetime object; verify the
        # string representation of the frontmatter line rather than the parsed type.
        assert "processed_date: 2026-03-23T12:00:00Z" in frontmatter_block
        assert parsed["domains"] == ["example.com"]


# ---------------------------------------------------------------------------
# TestGenerateResearchMarkdown
# ---------------------------------------------------------------------------


class TestGenerateResearchMarkdown:
    """Tests for generate_research_markdown."""

    def test_full_structure(self) -> None:
        """Should include frontmatter, H1 heading, Answer, Sources, and Related Questions."""
        sources = [
            SearchResult(title="MLX Docs", url="https://example.com/mlx", snippet="An array framework.", date=None)
        ]
        questions = ["How does MLX compare to PyTorch?"]
        result = _make_result(search_results=sources, related_questions=questions)
        markdown = generate_research_markdown(result)
        assert markdown.startswith("---\n")
        assert "tool: research" in markdown
        assert "# What is MLX?" in markdown
        assert "## Answer" in markdown
        assert "## Sources" in markdown
        assert "## Related Questions" in markdown

    def test_omits_sources_when_empty(self) -> None:
        """Should not include a Sources section when search_results is empty."""
        result = _make_result(search_results=[])
        markdown = generate_research_markdown(result)
        assert "## Sources" not in markdown

    def test_omits_related_questions_when_empty(self) -> None:
        """Should not include a Related Questions section when the list is empty."""
        result = _make_result(related_questions=[])
        markdown = generate_research_markdown(result)
        assert "## Related Questions" not in markdown

    def test_sources_format(self) -> None:
        """Should render each source as a numbered markdown link followed by an em-dash and snippet."""
        sources = [
            SearchResult(title="First Source", url="https://first.example.com", snippet="First snippet.", date=None),
            SearchResult(title="Second Source", url="https://second.example.com", snippet="Second snippet.", date=None),
        ]
        result = _make_result(search_results=sources)
        markdown = generate_research_markdown(result)
        assert "1. [First Source](https://first.example.com) — First snippet." in markdown
        assert "2. [Second Source](https://second.example.com) — Second snippet." in markdown

    def test_sources_without_snippet(self) -> None:
        """Should render a source link without the em-dash and snippet when snippet is None."""
        sources = [SearchResult(title="No Snippet Source", url="https://example.com", snippet=None, date=None)]
        result = _make_result(search_results=sources)
        markdown = generate_research_markdown(result)
        assert "1. [No Snippet Source](https://example.com)" in markdown
        assert " — " not in markdown

    def test_source_title_with_markdown_special_chars_is_escaped(self) -> None:
        """Should escape markdown special characters in source titles."""
        sources = [
            SearchResult(
                title="[MLX] Framework *Guide*",
                url="https://example.com/guide",
                snippet=None,
                date=None,
            )
        ]
        result = _make_result(search_results=sources)
        markdown = generate_research_markdown(result)
        assert r"\[MLX\] Framework \*Guide\*" in markdown

    def test_source_snippet_with_markdown_special_chars_is_escaped(self) -> None:
        """Should escape markdown special characters in source snippets."""
        sources = [
            SearchResult(
                title="Some Source",
                url="https://example.com",
                snippet="Use `code` and *emphasis* here.",
                date=None,
            )
        ]
        result = _make_result(search_results=sources)
        markdown = generate_research_markdown(result)
        assert r"\`code\` and \*emphasis\*" in markdown


# ---------------------------------------------------------------------------
# TestWriteResearchFile
# ---------------------------------------------------------------------------


class TestWriteResearchFile:
    """Tests for write_research_file."""

    def test_writes_to_correct_path(self, tmp_path: Path) -> None:
        """Should create a file named {date}_{slug}.md inside the output directory."""
        result = _make_result(query="What is MLX?", processed_date="2026-03-23T12:00:00Z")
        written_path = write_research_file("content", tmp_path, result)
        assert written_path.name == "260323-what-is-mlx.md"

    def test_creates_directories(self, tmp_path: Path) -> None:
        """Should create any missing parent directories before writing."""
        nested_output_dir = tmp_path / "research" / "export"
        result = _make_result()
        written_path = write_research_file("content", nested_output_dir, result)
        assert written_path.exists()

    def test_returns_path(self, tmp_path: Path) -> None:
        """Should return a Path instance pointing to the written file."""
        result = _make_result()
        written_path = write_research_file("some content", tmp_path, result)
        assert isinstance(written_path, Path)
        assert written_path.read_text(encoding="utf-8") == "some content"
