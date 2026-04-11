"""LLMs index file generator for the Stack Exchange tool.

Generates .llms.txt (titles and links) and .llms-full.txt (full content)
files at the rule output root directory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003
from typing import Any

from deep_thought.embeddings import strip_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class QuestionSummary:
    """Summary data for a collected question used in llms file generation."""

    title: str
    link: str
    relative_path: str
    rule_name: str
    score: int
    answer_count: int
    content: str  # frontmatter-stripped markdown


def build_summaries_from_directory(rule_output_dir: Path) -> list[QuestionSummary]:
    """Build a QuestionSummary list from markdown files in a rule output directory.

    Reads each .md file, strips frontmatter, and extracts metadata from the
    frontmatter block for the summary. Files that cannot be read or parsed
    are logged as warnings and skipped.

    Args:
        rule_output_dir: Directory containing per-question markdown files.

    Returns:
        List of QuestionSummary objects sorted by filename (alphabetical).
        Returns an empty list if the directory does not exist.
    """
    summaries: list[QuestionSummary] = []
    if not rule_output_dir.exists():
        return summaries

    import yaml

    for markdown_file in sorted(rule_output_dir.glob("*.md")):
        try:
            raw_text = markdown_file.read_text(encoding="utf-8")
            stripped_content = strip_frontmatter(raw_text)

            # Parse frontmatter manually to extract metadata fields
            frontmatter: dict[str, Any] = {}
            if raw_text.startswith("---"):
                frontmatter_end_index = raw_text.find("\n---", 3)
                if frontmatter_end_index != -1:
                    frontmatter_text = raw_text[4:frontmatter_end_index]
                    parsed_yaml = yaml.safe_load(frontmatter_text)
                    if isinstance(parsed_yaml, dict):
                        frontmatter = parsed_yaml

            summaries.append(
                QuestionSummary(
                    title=str(frontmatter.get("title", markdown_file.stem)),
                    link=str(frontmatter.get("link", "")),
                    relative_path=markdown_file.name,
                    rule_name=str(frontmatter.get("rule", "")),
                    score=int(frontmatter.get("score", 0)),
                    answer_count=int(frontmatter.get("answer_count", 0)),
                    content=stripped_content,
                )
            )
        except Exception:
            logger.warning("Failed to read %s for llms generation", markdown_file.name, exc_info=True)

    return summaries


def write_llms_index(summaries: list[QuestionSummary], output_dir: Path) -> Path:
    """Write a .llms.txt index file listing titles and links for all collected questions.

    The index file is a lightweight reference that allows a consumer to scan
    what is available without loading full content.

    Args:
        summaries: List of question summaries to include in the index.
        output_dir: Directory to write the .llms.txt file into.

    Returns:
        Path to the written .llms.txt file.
    """
    output_path = output_dir / ".llms.txt"
    lines: list[str] = ["# Stack Exchange Collection Index", ""]
    for summary in summaries:
        lines.append(f"- [{summary.title}]({summary.link}) (score: {summary.score}, answers: {summary.answer_count})")
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote llms index: %s (%d entries)", output_path, len(summaries))
    return output_path


def write_llms_full(summaries: list[QuestionSummary], output_dir: Path) -> Path:
    """Write a .llms-full.txt file containing the complete content of all collected questions.

    Each question is rendered as a titled section with source metadata followed
    by its full frontmatter-stripped markdown body. A horizontal rule separates
    questions for easy parsing.

    Args:
        summaries: List of question summaries whose content will be concatenated.
        output_dir: Directory to write the .llms-full.txt file into.

    Returns:
        Path to the written .llms-full.txt file.
    """
    output_path = output_dir / ".llms-full.txt"
    sections: list[str] = ["# Stack Exchange Collection \u2014 Full Content", ""]
    for summary in summaries:
        sections.append(f"## {summary.title}")
        sections.append(f"Source: {summary.link}")
        sections.append(f"Score: {summary.score} | Answers: {summary.answer_count}")
        sections.append("")
        sections.append(summary.content)
        sections.append("")
        sections.append("---")
        sections.append("")
    output_path.write_text("\n".join(sections), encoding="utf-8")
    logger.info("Wrote llms full: %s (%d entries)", output_path, len(summaries))
    return output_path
