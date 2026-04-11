"""Markdown and YAML frontmatter generator for the Stack Exchange Tool.

Converts a Stack Exchange API question dict, its answers, and comments into a
structured markdown file with machine-readable YAML frontmatter. Claude is the
primary consumer; formatting decisions optimize for machine parsing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path  # noqa: TC003
from typing import Any

from deep_thought.text_utils import slugify

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escape_yaml_string(text: str) -> str:
    """Escape a string for safe embedding inside a double-quoted YAML value.

    Escapes backslashes, double quotes, and literal newlines/carriage returns
    so the result is safe to place between double-quote delimiters in YAML
    frontmatter without breaking the parser.

    Args:
        text: The raw string to escape.

    Returns:
        The escaped string, suitable for use as: title: "{escaped}"
    """
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def count_words(text: str) -> int:
    """Return an approximate word count for a string.

    Splits on whitespace — suitable for estimating document length without
    accounting for markdown syntax tokens.

    Args:
        text: Any string, typically the body of a generated markdown document.

    Returns:
        Number of whitespace-separated tokens in text.
    """
    return len(text.split())


# ---------------------------------------------------------------------------
# Frontmatter builder
# ---------------------------------------------------------------------------


def _build_frontmatter(
    question: dict[str, Any],
    rule_name: str,
    site: str,
    word_count: int,
    processed_date: str,
) -> str:
    """Build the YAML frontmatter block for a question's markdown file.

    Args:
        question: A Stack Exchange API question dict.
        rule_name: The name of the collection rule that retrieved this question.
        site: The Stack Exchange site slug (e.g., "stackoverflow").
        word_count: Word count of the full generated content (computed by caller).
        processed_date: ISO 8601 UTC timestamp string for when processing occurred.

    Returns:
        A string containing the full YAML frontmatter block including the
        opening and closing ``---`` delimiters and a trailing newline.
    """
    question_id = int(question["question_id"])
    state_key = f"{question_id}:{site}:{rule_name}"
    title = str(question.get("title", ""))
    link = str(question.get("link", ""))
    score = int(question.get("score", 0))
    answer_count = int(question.get("answer_count", 0))
    accepted_answer_id = question.get("accepted_answer_id")
    has_accepted_answer = accepted_answer_id is not None
    raw_tags = question.get("tags", [])
    tags: list[str] = list(raw_tags) if isinstance(raw_tags, list) else json.loads(raw_tags)

    lines: list[str] = ["---"]
    lines.append("tool: stackexchange")
    lines.append(f"state_key: {state_key}")
    lines.append(f"question_id: {question_id}")
    lines.append(f"site: {site}")
    lines.append(f"rule: {rule_name}")
    lines.append(f'title: "{_escape_yaml_string(title)}"')
    lines.append(f'link: "{_escape_yaml_string(link)}"')
    lines.append(f"score: {score}")
    lines.append(f"answer_count: {answer_count}")
    lines.append(f"accepted_answer: {str(has_accepted_answer).lower()}")
    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {tag}")
    lines.append(f"word_count: {word_count}")
    lines.append(f"processed_date: {processed_date}")
    lines.append("---")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Comment rendering
# ---------------------------------------------------------------------------


def _render_comments(comments: list[dict[str, Any]]) -> str:
    """Render a list of Stack Exchange comment dicts as a markdown blockquote block.

    Each comment is rendered as a single blockquote line:
    ``> **username (↑ N):** comment text``

    Args:
        comments: List of comment dicts from the Stack Exchange API.
                  Each dict is expected to have body, score, and owner fields.

    Returns:
        A markdown string with one blockquote per comment, or an empty string
        if the comments list is empty.
    """
    if not comments:
        return ""

    rendered_lines: list[str] = []
    for comment in comments:
        owner = comment.get("owner", {})
        display_name = str(owner.get("display_name", "unknown")) if isinstance(owner, dict) else "unknown"
        comment_score = int(comment.get("score", 0))
        comment_body = str(comment.get("body", "")).strip()
        rendered_lines.append(f"> **{display_name} (\u2191 {comment_score}):** {comment_body}")

    return "\n".join(rendered_lines)


# ---------------------------------------------------------------------------
# Answer rendering
# ---------------------------------------------------------------------------


def _render_answer(
    answer: dict[str, Any],
    is_accepted: bool,
    answer_comments: list[dict[str, Any]],
) -> str:
    """Render a single Stack Exchange answer and its comments as a markdown section.

    The heading distinguishes accepted answers with a checkmark prefix and the
    "Accepted Answer" label. Non-accepted answers use a plain "Answer" label.
    Vote score and answerer username appear in the heading line.

    Args:
        answer: A Stack Exchange API answer dict.
        is_accepted: Whether this answer is the accepted answer for the question.
        answer_comments: List of comment dicts for this answer.

    Returns:
        A markdown string for the answer section including any comments.
    """
    owner = answer.get("owner", {})
    display_name = str(owner.get("display_name", "unknown")) if isinstance(owner, dict) else "unknown"
    answer_score = int(answer.get("score", 0))
    body_markdown = str(answer.get("body_markdown", "")).strip()

    if is_accepted:
        heading = f"## Accepted Answer (\u2191 {answer_score}) \u2014 answered by {display_name}"
    else:
        heading = f"## Answer (\u2191 {answer_score}) \u2014 answered by {display_name}"

    answer_parts: list[str] = [heading, "", body_markdown]

    if answer_comments:
        comments_block = _render_comments(answer_comments)
        answer_parts.extend(["", "### Comments", "", comments_block])

    return "\n".join(answer_parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_markdown(
    question: dict[str, Any],
    answers: list[dict[str, Any]],
    question_comments: list[dict[str, Any]],
    answer_comments: dict[int, list[dict[str, Any]]],
    rule_name: str,
    site: str,
) -> str:
    """Generate the full markdown content (frontmatter + question + answers) for a Q&A thread.

    The accepted answer is rendered first (if present), followed by remaining
    answers ordered by their position in the answers list. Question-level
    comments follow the question body. Answer-level comments are attached to
    each answer section.

    Args:
        question: A Stack Exchange API question dict.
        answers: List of answer dicts for this question (pre-sorted by caller).
        question_comments: List of comment dicts on the question itself.
        answer_comments: Dict mapping answer_id to list of comment dicts for that answer.
        rule_name: The collection rule name (written to frontmatter).
        site: The Stack Exchange site slug (e.g., "stackoverflow").

    Returns:
        A complete markdown string ready to write to disk.
    """
    from datetime import UTC, datetime

    processed_date = datetime.now(tz=UTC).isoformat()

    title = str(question.get("title", ""))
    score = int(question.get("score", 0))
    answer_count = int(question.get("answer_count", 0))
    raw_tags = question.get("tags", [])
    tags: list[str] = list(raw_tags) if isinstance(raw_tags, list) else []
    tags_display = ", ".join(tags) if tags else "none"
    body_markdown = str(question.get("body_markdown", "")).strip()
    accepted_answer_id: int | None = question.get("accepted_answer_id")

    # Build body header
    header_line = f"**Score:** {score} | **Answers:** {answer_count} | **Tags:** {tags_display}"

    body_parts: list[str] = [
        f"# {title}",
        "",
        header_line,
        "",
        "## Question",
        "",
        body_markdown,
    ]

    # Question comments
    if question_comments:
        rendered_question_comments = _render_comments(question_comments)
        body_parts.extend(["", "### Comments on Question", "", rendered_question_comments])

    body_parts.append("\n---")

    # Sort answers: accepted first, then by position
    sorted_answers: list[dict[str, Any]] = []
    non_accepted_answers: list[dict[str, Any]] = []

    for answer in answers:
        answer_id = int(answer.get("answer_id", 0))
        if accepted_answer_id is not None and answer_id == accepted_answer_id:
            sorted_answers.append(answer)
        else:
            non_accepted_answers.append(answer)

    sorted_answers.extend(non_accepted_answers)

    # Render each answer
    for answer in sorted_answers:
        answer_id = int(answer.get("answer_id", 0))
        is_accepted = accepted_answer_id is not None and answer_id == accepted_answer_id
        comments_for_answer = answer_comments.get(answer_id, [])
        rendered_answer = _render_answer(answer, is_accepted, comments_for_answer)
        body_parts.extend(["", rendered_answer])

    full_body = "\n".join(body_parts)
    word_count = count_words(full_body)

    frontmatter = _build_frontmatter(question, rule_name, site, word_count, processed_date)

    return f"{frontmatter}\n{full_body}"


def write_question_file(
    content: str,
    output_dir: Path,
    rule_name: str,
    question_id: int,
    title: str,
    date_prefix: str,
) -> Path:
    """Write a question's markdown content to disk under the rule's output directory.

    File naming: ``{date_prefix}_{question_id}_{title_slug}.md``
    Directory: ``{output_dir}/{rule_name}/``

    Args:
        content: Full markdown content string to write.
        output_dir: Root output directory (e.g., data/stackexchange/export/).
        rule_name: The name of the rule, used as a subdirectory name.
        question_id: The Stack Exchange question ID, included in the filename.
        title: The question title, slugified for the filename.
        date_prefix: Pre-computed YYMMDD date string from the caller.

    Returns:
        The Path to the written markdown file.
    """
    rule_output_dir = output_dir / rule_name
    rule_output_dir.mkdir(parents=True, exist_ok=True)

    title_slug = slugify(title, max_length=60, empty_fallback="no-title")
    filename = f"{date_prefix}_{question_id}_{title_slug}.md"

    output_path = rule_output_dir / filename
    output_path.write_text(content, encoding="utf-8")

    return output_path
