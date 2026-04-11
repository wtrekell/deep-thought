"""Tests for markdown generation in deep_thought.stackexchange.output.

Tests verify that question/answer/comment content appears in generated
output and that files are written to the expected locations.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

from deep_thought.stackexchange.output import (
    _build_frontmatter,
    _escape_yaml_string,
    generate_markdown,
    write_question_file,
)
from tests.stackexchange.conftest import make_mock_answer, make_mock_comment, make_mock_question

# ---------------------------------------------------------------------------
# TestGenerateMarkdown
# ---------------------------------------------------------------------------


class TestGenerateMarkdown:
    def test_output_contains_title(self) -> None:
        """The generated markdown should contain the question title."""
        question = make_mock_question(title="How do I reverse a Python list?")
        result = generate_markdown(
            question=question,
            answers=[],
            question_comments=[],
            answer_comments={},
            rule_name="test_rule",
            site="stackoverflow",
        )
        assert "How do I reverse a Python list?" in result

    def test_output_contains_question_body(self) -> None:
        """The generated markdown should contain the question body_markdown."""
        question = make_mock_question(body_markdown="This is the question body content.")
        result = generate_markdown(
            question=question,
            answers=[],
            question_comments=[],
            answer_comments={},
            rule_name="test_rule",
            site="stackoverflow",
        )
        assert "This is the question body content." in result

    def test_output_contains_answer_body(self) -> None:
        """The generated markdown should contain the body of each answer."""
        question = make_mock_question()
        answer = make_mock_answer(body_markdown="This is the answer body.", is_accepted=False)
        result = generate_markdown(
            question=question,
            answers=[answer],
            question_comments=[],
            answer_comments={},
            rule_name="test_rule",
            site="stackoverflow",
        )
        assert "This is the answer body." in result

    def test_accepted_answer_rendered_first(self) -> None:
        """The accepted answer should appear before non-accepted answers."""
        question = make_mock_question(accepted_answer_id=67890)
        accepted_answer = make_mock_answer(answer_id=67890, body_markdown="Accepted answer body.", is_accepted=True)
        other_answer = make_mock_answer(
            answer_id=11111, question_id=12345, body_markdown="Other answer body.", is_accepted=False
        )
        result = generate_markdown(
            question=question,
            answers=[other_answer, accepted_answer],
            question_comments=[],
            answer_comments={},
            rule_name="test_rule",
            site="stackoverflow",
        )
        accepted_position = result.find("Accepted answer body.")
        other_position = result.find("Other answer body.")
        assert accepted_position < other_position

    def test_output_contains_question_comment_body(self) -> None:
        """The generated markdown should contain question comment text."""
        question = make_mock_question()
        comment = make_mock_comment(body="This is a question comment.")
        result = generate_markdown(
            question=question,
            answers=[],
            question_comments=[comment],
            answer_comments={},
            rule_name="test_rule",
            site="stackoverflow",
        )
        assert "This is a question comment." in result

    def test_output_contains_frontmatter_block(self) -> None:
        """The generated markdown should contain YAML frontmatter delimiters."""
        question = make_mock_question()
        result = generate_markdown(
            question=question,
            answers=[],
            question_comments=[],
            answer_comments={},
            rule_name="test_rule",
            site="stackoverflow",
        )
        assert result.startswith("---")
        assert "tool: stackexchange" in result

    def test_empty_answers_produces_no_answer_sections(self) -> None:
        """When there are no answers, no answer headers should appear in the output."""
        question = make_mock_question()
        result = generate_markdown(
            question=question,
            answers=[],
            question_comments=[],
            answer_comments={},
            rule_name="test_rule",
            site="stackoverflow",
        )
        assert "## Answer" not in result
        assert "## Accepted Answer" not in result


# ---------------------------------------------------------------------------
# TestBuildFrontmatter
# ---------------------------------------------------------------------------


class TestBuildFrontmatter:
    def _call_build_frontmatter(
        self,
        question: dict[str, Any],
        rule_name: str = "test_rule",
        site: str = "stackoverflow",
    ) -> str:
        """Helper to call _build_frontmatter with minimal boilerplate."""
        return _build_frontmatter(
            question=question,
            rule_name=rule_name,
            site=site,
            word_count=100,
            processed_date="2026-04-11T00:00:00+00:00",
        )

    def test_contains_tool_field(self) -> None:
        """The frontmatter should include 'tool: stackexchange'."""
        question = make_mock_question()
        result = self._call_build_frontmatter(question)
        assert "tool: stackexchange" in result

    def test_contains_question_id(self) -> None:
        """The frontmatter should include the question_id field."""
        question = make_mock_question(question_id=99999)
        result = self._call_build_frontmatter(question)
        assert "question_id: 99999" in result

    def test_contains_site(self) -> None:
        """The frontmatter should include the site field."""
        question = make_mock_question()
        result = self._call_build_frontmatter(question, site="superuser")
        assert "site: superuser" in result

    def test_contains_rule_name(self) -> None:
        """The frontmatter should include the rule field."""
        question = make_mock_question()
        result = self._call_build_frontmatter(question, rule_name="my_custom_rule")
        assert "rule: my_custom_rule" in result

    def test_contains_score(self) -> None:
        """The frontmatter should include the score field."""
        question = make_mock_question(score=250)
        result = self._call_build_frontmatter(question)
        assert "score: 250" in result

    def test_contains_state_key(self) -> None:
        """The frontmatter should include the state_key field."""
        question = make_mock_question(question_id=12345)
        result = self._call_build_frontmatter(question, rule_name="test_rule", site="stackoverflow")
        assert "state_key: 12345:stackoverflow:test_rule" in result

    def test_contains_all_expected_fields(self) -> None:
        """The frontmatter should contain all expected metadata fields."""
        question = make_mock_question()
        result = self._call_build_frontmatter(question)
        for field_name in [
            "tool",
            "state_key",
            "question_id",
            "site",
            "rule",
            "title",
            "link",
            "score",
            "answer_count",
            "accepted_answer",
            "tags",
            "word_count",
            "processed_date",
        ]:
            assert field_name in result, f"Missing field: {field_name}"

    def test_starts_and_ends_with_delimiter(self) -> None:
        """The frontmatter should start with '---' and end with '---'."""
        question = make_mock_question()
        result = self._call_build_frontmatter(question)
        assert result.startswith("---")
        assert "---" in result[3:]  # closing delimiter


# ---------------------------------------------------------------------------
# TestWriteQuestionFile
# ---------------------------------------------------------------------------


class TestWriteQuestionFile:
    def test_file_is_created(self, tmp_path: Path) -> None:
        """write_question_file should create a markdown file on disk."""
        written_path = write_question_file(
            content="# Test Question\n\nBody content.",
            output_dir=tmp_path,
            rule_name="test_rule",
            question_id=12345,
            title="How do I reverse a list?",
            date_prefix="260411",
        )
        assert written_path.exists()

    def test_file_has_correct_name_format(self, tmp_path: Path) -> None:
        """The written file name should follow the pattern: {date_prefix}_{question_id}_{slug}.md."""
        written_path = write_question_file(
            content="content",
            output_dir=tmp_path,
            rule_name="test_rule",
            question_id=99999,
            title="My Test Question",
            date_prefix="260411",
        )
        assert written_path.name.startswith("260411_99999_")
        assert written_path.suffix == ".md"

    def test_file_is_in_rule_subdirectory(self, tmp_path: Path) -> None:
        """The written file should be inside a subdirectory named after the rule."""
        written_path = write_question_file(
            content="content",
            output_dir=tmp_path,
            rule_name="my_rule_name",
            question_id=11111,
            title="Some Question",
            date_prefix="260411",
        )
        assert written_path.parent.name == "my_rule_name"

    def test_file_contains_written_content(self, tmp_path: Path) -> None:
        """The written file should contain the exact content passed in."""
        test_content = "# Special Content\n\nThis is unique content for assertion."
        written_path = write_question_file(
            content=test_content,
            output_dir=tmp_path,
            rule_name="test_rule",
            question_id=22222,
            title="Title",
            date_prefix="260411",
        )
        assert written_path.read_text(encoding="utf-8") == test_content

    def test_creates_rule_directory_if_missing(self, tmp_path: Path) -> None:
        """write_question_file should create the rule subdirectory if it does not exist."""
        rule_dir = tmp_path / "new_rule_dir"
        assert not rule_dir.exists()
        write_question_file(
            content="content",
            output_dir=tmp_path,
            rule_name="new_rule_dir",
            question_id=33333,
            title="Test",
            date_prefix="260411",
        )
        assert rule_dir.exists()


# ---------------------------------------------------------------------------
# TestEscapeYamlString
# ---------------------------------------------------------------------------


class TestEscapeYamlString:
    def test_escapes_double_quotes(self) -> None:
        """Double quotes in the text should be escaped with a backslash."""
        result = _escape_yaml_string('She said "hello".')
        assert '\\"' in result

    def test_escapes_backslashes(self) -> None:
        """Backslashes should be doubled to prevent YAML misinterpretation."""
        result = _escape_yaml_string("path\\to\\file")
        assert "\\\\" in result

    def test_escapes_newlines(self) -> None:
        """Literal newlines should be replaced with \\n escape sequences."""
        result = _escape_yaml_string("line one\nline two")
        assert "\\n" in result
        assert "\n" not in result

    def test_escapes_carriage_returns(self) -> None:
        """Carriage returns should be replaced with \\r escape sequences."""
        result = _escape_yaml_string("line one\r\nline two")
        assert "\\r" in result

    def test_plain_text_unchanged(self) -> None:
        """Text without special characters should not be modified."""
        plain_text = "A perfectly normal question title"
        result = _escape_yaml_string(plain_text)
        assert result == plain_text
