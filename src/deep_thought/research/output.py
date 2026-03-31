"""Markdown output generation for the Research Tool."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from deep_thought.research.models import ResearchResult


# ---------------------------------------------------------------------------
# Markdown escaping
# ---------------------------------------------------------------------------

_MARKDOWN_SPECIAL_CHARS_RE = re.compile(r"([`*_\[\]])")


def _escape_markdown(text: str) -> str:
    """Escape markdown special characters in a plain-text string.

    Escapes backticks, asterisks, underscores, and square brackets so that
    the string is safe to embed inside markdown link syntax (``[title](url)``).

    Args:
        text: The raw string to escape.

    Returns:
        The escaped string with ``\\`` prepended to each special character.
    """
    return _MARKDOWN_SPECIAL_CHARS_RE.sub(r"\\\1", text)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG_LENGTH = 80


def _slugify(text: str, max_length: int = _MAX_SLUG_LENGTH) -> str:
    """Convert text to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric runs with hyphens,
    strips leading/trailing hyphens, and truncates.

    Args:
        text: The text to slugify.
        max_length: Maximum slug length.

    Returns:
        A filesystem-safe slug, or "no-title" if the result is empty.
    """
    slug = _NON_ALNUM_RE.sub("-", text.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug if slug else "no-title"


# ---------------------------------------------------------------------------
# Frontmatter generation
# ---------------------------------------------------------------------------


def _escape_yaml_value(value: str) -> str:
    """Escape a string for safe inclusion in YAML double-quoted values.

    Escapes backslashes, double quotes, newlines, carriage returns, and tabs
    so the resulting string is valid inside YAML double-quoted scalars.

    Args:
        value: The raw string value.

    Returns:
        The escaped string safe for YAML double-quoted context.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _build_frontmatter(result: ResearchResult) -> str:
    """Build YAML frontmatter from a ResearchResult.

    Always includes tool, query, mode, model, cost_usd, and processed_date.
    Conditionally includes recency, domains, and context_files when present.

    Args:
        result: A ResearchResult dataclass instance.

    Returns:
        A YAML frontmatter string including the --- delimiters.
    """
    lines = ["---"]
    lines.append("tool: research")

    escaped_query = _escape_yaml_value(result.query)
    lines.append(f'query: "{escaped_query}"')

    lines.append(f"mode: {result.mode}")
    lines.append(f"model: {result.model}")
    cost_formatted = f"{result.cost_usd:.6f}".rstrip("0").rstrip(".")
    lines.append(f"cost_usd: {cost_formatted}")
    lines.append(f"processed_date: {result.processed_date}")

    if result.recency is not None:
        lines.append(f"recency: {result.recency}")

    if result.domains:
        lines.append("domains:")
        for domain in result.domains:
            escaped_domain = _escape_yaml_value(domain)
            lines.append(f'  - "{escaped_domain}"')

    if result.context_files:
        lines.append("context_files:")
        for context_file_path in result.context_files:
            escaped_path = _escape_yaml_value(context_file_path)
            lines.append(f'  - "{escaped_path}"')

    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def generate_research_markdown(result: ResearchResult) -> str:
    """Generate a complete markdown document for a single research result.

    Assembles YAML frontmatter, the query as an H1 heading, the synthesized
    answer, an optional numbered sources list, and optional related questions.
    Sections with no content are omitted.

    Args:
        result: A ResearchResult dataclass instance.

    Returns:
        A complete markdown string ready to write to disk.
    """
    frontmatter = _build_frontmatter(result)
    sections: list[str] = [frontmatter, f"# {result.query}", "## Answer", result.answer]

    if result.search_results:
        source_lines = ["## Sources", ""]
        for index, source in enumerate(result.search_results, start=1):
            escaped_title = _escape_markdown(source.title)
            source_link = f"[{escaped_title}]({source.url})"
            if source.snippet is not None:
                escaped_snippet = _escape_markdown(source.snippet)
                source_lines.append(f"{index}. {source_link} — {escaped_snippet}")
            else:
                source_lines.append(f"{index}. {source_link}")
        sections.append("\n".join(source_lines))

    if result.related_questions:
        question_lines = ["## Related Questions", ""]
        for question in result.related_questions:
            question_lines.append(f"- {question}")
        sections.append("\n".join(question_lines))

    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def write_research_file(content: str, output_dir: Path, result: ResearchResult) -> Path:
    """Write a single research result's markdown content to a file.

    The filename is derived from the result's processed date and a slug of
    the query: ``{date}_{slug}.md``. The output directory is created if it
    does not already exist.

    Args:
        content: The full markdown content to write.
        output_dir: The directory in which to create the file.
        result: The ResearchResult used to derive the filename.

    Returns:
        The Path to the written file.
    """
    raw_date = result.processed_date[:10]  # "2026-03-24"
    date_prefix = raw_date[2:4] + raw_date[5:7] + raw_date[8:10]  # "260324"
    query_slug = _slugify(result.query)
    filename = f"{date_prefix}-{query_slug}.md"

    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path
