"""Tests for LLMs index file generation in deep_thought.stackexchange.llms.

Tests verify that index and full-content files are created with the correct
structure and that content from question summaries is included.
"""

from __future__ import annotations

from pathlib import Path

from deep_thought.stackexchange.llms import (
    QuestionSummary,
    build_summaries_from_directory,
    write_llms_full,
    write_llms_index,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_question_summary(
    title: str = "How do I reverse a Python list?",
    link: str = "https://stackoverflow.com/questions/12345/test",
    relative_path: str = "260411_12345_test.md",
    rule_name: str = "test_rule",
    score: int = 150,
    answer_count: int = 5,
    content: str = "This is the full question content without frontmatter.",
) -> QuestionSummary:
    """Return a QuestionSummary with configurable test values.

    Args:
        title: The question title.
        link: The URL to the question on Stack Exchange.
        relative_path: Relative filename for the markdown file.
        rule_name: The collection rule name.
        score: Vote score.
        answer_count: Number of answers.
        content: Frontmatter-stripped markdown body.

    Returns:
        A QuestionSummary instance.
    """
    return QuestionSummary(
        title=title,
        link=link,
        relative_path=relative_path,
        rule_name=rule_name,
        score=score,
        answer_count=answer_count,
        content=content,
    )


# ---------------------------------------------------------------------------
# TestWriteLlmsIndex
# ---------------------------------------------------------------------------


class TestWriteLlmsIndex:
    def test_file_is_created(self, tmp_path: Path) -> None:
        """write_llms_index should create a .llms.txt file in the output directory."""
        summaries = [_make_question_summary()]
        written_path = write_llms_index(summaries, tmp_path)
        assert written_path.exists()
        assert written_path.name == ".llms.txt"

    def test_content_includes_titles(self, tmp_path: Path) -> None:
        """The .llms.txt file should contain the title of each question."""
        summaries = [
            _make_question_summary(title="How do I reverse a Python list?"),
            _make_question_summary(title="What is the difference between list and tuple?"),
        ]
        written_path = write_llms_index(summaries, tmp_path)
        file_content = written_path.read_text(encoding="utf-8")
        assert "How do I reverse a Python list?" in file_content
        assert "What is the difference between list and tuple?" in file_content

    def test_content_includes_links(self, tmp_path: Path) -> None:
        """The .llms.txt file should contain links to the source questions."""
        summaries = [_make_question_summary(link="https://stackoverflow.com/questions/99999/test")]
        written_path = write_llms_index(summaries, tmp_path)
        file_content = written_path.read_text(encoding="utf-8")
        assert "https://stackoverflow.com/questions/99999/test" in file_content

    def test_content_includes_score(self, tmp_path: Path) -> None:
        """The .llms.txt file should contain the score for each question."""
        summaries = [_make_question_summary(score=999)]
        written_path = write_llms_index(summaries, tmp_path)
        file_content = written_path.read_text(encoding="utf-8")
        assert "999" in file_content

    def test_empty_summaries_creates_file(self, tmp_path: Path) -> None:
        """write_llms_index should create the file even with an empty summaries list."""
        written_path = write_llms_index([], tmp_path)
        assert written_path.exists()

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """write_llms_index should return the Path of the written file."""
        summaries = [_make_question_summary()]
        result = write_llms_index(summaries, tmp_path)
        assert isinstance(result, Path)
        assert result == tmp_path / ".llms.txt"


# ---------------------------------------------------------------------------
# TestWriteLlmsFull
# ---------------------------------------------------------------------------


class TestWriteLlmsFull:
    def test_file_is_created(self, tmp_path: Path) -> None:
        """write_llms_full should create a .llms-full.txt file in the output directory."""
        summaries = [_make_question_summary()]
        written_path = write_llms_full(summaries, tmp_path)
        assert written_path.exists()
        assert written_path.name == ".llms-full.txt"

    def test_content_includes_full_markdown(self, tmp_path: Path) -> None:
        """The .llms-full.txt file should contain the full content of each question."""
        unique_content = "This is uniquely identifiable content for assertion purposes."
        summaries = [_make_question_summary(content=unique_content)]
        written_path = write_llms_full(summaries, tmp_path)
        file_content = written_path.read_text(encoding="utf-8")
        assert unique_content in file_content

    def test_content_includes_all_titles(self, tmp_path: Path) -> None:
        """The .llms-full.txt file should contain titles from all summaries."""
        summaries = [
            _make_question_summary(title="First Question Title"),
            _make_question_summary(title="Second Question Title"),
        ]
        written_path = write_llms_full(summaries, tmp_path)
        file_content = written_path.read_text(encoding="utf-8")
        assert "First Question Title" in file_content
        assert "Second Question Title" in file_content

    def test_content_includes_source_links(self, tmp_path: Path) -> None:
        """The .llms-full.txt file should include the source URL for each question."""
        summaries = [_make_question_summary(link="https://stackoverflow.com/questions/55555/test")]
        written_path = write_llms_full(summaries, tmp_path)
        file_content = written_path.read_text(encoding="utf-8")
        assert "https://stackoverflow.com/questions/55555/test" in file_content

    def test_empty_summaries_creates_file(self, tmp_path: Path) -> None:
        """write_llms_full should create the file even with an empty summaries list."""
        written_path = write_llms_full([], tmp_path)
        assert written_path.exists()

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """write_llms_full should return the Path of the written file."""
        summaries = [_make_question_summary()]
        result = write_llms_full(summaries, tmp_path)
        assert isinstance(result, Path)
        assert result == tmp_path / ".llms-full.txt"

    def test_sections_separated_by_horizontal_rule(self, tmp_path: Path) -> None:
        """Multiple summaries should be separated by horizontal rule markers."""
        summaries = [
            _make_question_summary(title="First"),
            _make_question_summary(title="Second"),
        ]
        written_path = write_llms_full(summaries, tmp_path)
        file_content = written_path.read_text(encoding="utf-8")
        assert "---" in file_content


# ---------------------------------------------------------------------------
# TestBuildSummariesFromDirectory
# ---------------------------------------------------------------------------

_VALID_MD = """\
---
tool: stackexchange
title: "How do I reverse a list?"
link: "https://stackoverflow.com/questions/12345/test"
rule: test_rule
score: 42
answer_count: 3
---

# How do I reverse a list?

Use `list.reverse()` or `reversed()`.
"""

_MALFORMED_FM = """\
---
this is not: valid: yaml: [[[
---

Some content here.
"""


class TestBuildSummariesFromDirectory:
    def test_reads_valid_markdown_files(self, tmp_path: Path) -> None:
        """build_summaries_from_directory should parse valid markdown files with frontmatter."""
        md_file = tmp_path / "260411_12345_test.md"
        md_file.write_text(_VALID_MD, encoding="utf-8")

        summaries = build_summaries_from_directory(tmp_path)
        assert len(summaries) == 1
        assert summaries[0].title == "How do I reverse a list?"
        assert summaries[0].score == 42
        assert summaries[0].answer_count == 3

    def test_skips_malformed_frontmatter_gracefully(self, tmp_path: Path) -> None:
        """Malformed frontmatter should be logged as a warning, not crash."""
        bad_file = tmp_path / "260411_99999_bad.md"
        bad_file.write_text(_MALFORMED_FM, encoding="utf-8")

        summaries = build_summaries_from_directory(tmp_path)
        # Should either return a summary with fallback values or skip — not crash
        assert isinstance(summaries, list)

    def test_returns_empty_for_nonexistent_directory(self) -> None:
        """build_summaries_from_directory should return an empty list for a missing directory."""
        summaries = build_summaries_from_directory(Path("/nonexistent/dir/12345"))
        assert summaries == []

    def test_ignores_non_markdown_files(self, tmp_path: Path) -> None:
        """Non-.md files in the directory should be ignored."""
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("not a markdown file", encoding="utf-8")
        md_file = tmp_path / "260411_12345_test.md"
        md_file.write_text(_VALID_MD, encoding="utf-8")

        summaries = build_summaries_from_directory(tmp_path)
        assert len(summaries) == 1

    def test_content_has_frontmatter_stripped(self, tmp_path: Path) -> None:
        """The content field should not contain YAML frontmatter."""
        md_file = tmp_path / "260411_12345_test.md"
        md_file.write_text(_VALID_MD, encoding="utf-8")

        summaries = build_summaries_from_directory(tmp_path)
        assert len(summaries) == 1
        assert "---" not in summaries[0].content
        assert "tool: stackexchange" not in summaries[0].content
        assert "reverse" in summaries[0].content
