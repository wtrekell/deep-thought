"""LLM context file generation for the Gmail Tool.

Generates .llms.txt and .llms-full.txt files for collected emails,
controlled by the generate_llms_files configuration setting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def strip_frontmatter(markdown_text: str) -> str:
    """Remove YAML frontmatter from a markdown string.

    Args:
        markdown_text: A markdown string that may start with --- delimited frontmatter.

    Returns:
        The markdown text with frontmatter removed.
    """
    if not markdown_text.startswith("---"):
        return markdown_text

    # Find the closing ---
    end_index = markdown_text.find("---", 3)
    if end_index == -1:
        return markdown_text

    return markdown_text[end_index + 3 :].strip()


def generate_llms_index(
    email_files: list[Path],
    rule_name: str,
) -> str:
    """Generate a .llms.txt index of all email files for a rule.

    Lists each file with its path and first non-empty line as a summary.

    Args:
        email_files: List of markdown file paths.
        rule_name: The rule name for the header.

    Returns:
        The .llms.txt content as a string.
    """
    lines = [f"# {rule_name} — Email Index", ""]

    for file_path in email_files:
        text = file_path.read_text(encoding="utf-8")
        body = strip_frontmatter(text)
        first_line = ""
        for line in body.splitlines():
            stripped = line.strip()
            if stripped:
                first_line = stripped[:120]
                break
        lines.append(f"- {file_path.name}: {first_line}")

    return "\n".join(lines) + "\n"


def generate_llms_full(
    email_files: list[Path],
    rule_name: str,
) -> str:
    """Generate a .llms-full.txt with all email content concatenated.

    Each email is separated by a horizontal rule.

    Args:
        email_files: List of markdown file paths.
        rule_name: The rule name for the header.

    Returns:
        The .llms-full.txt content as a string.
    """
    sections = [f"# {rule_name} — Full Email Content"]

    for file_path in email_files:
        text = file_path.read_text(encoding="utf-8")
        body = strip_frontmatter(text)
        sections.append(f"\n---\n\n## {file_path.name}\n\n{body}")

    return "\n".join(sections) + "\n"


def write_llms_files(
    email_files: list[Path],
    output_dir: Path,
    rule_name: str,
) -> None:
    """Write .llms.txt and .llms-full.txt files for a rule.

    Files are placed in {output_dir}/{rule_name}/llm/.

    Args:
        email_files: List of markdown file paths for this rule.
        output_dir: The root output directory.
        rule_name: The rule name (used as subdirectory).
    """
    if not email_files:
        return

    llm_dir = output_dir / rule_name / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)

    index_content = generate_llms_index(email_files, rule_name)
    index_path = llm_dir / f"{rule_name}.llms.txt"
    index_path.write_text(index_content, encoding="utf-8")

    full_content = generate_llms_full(email_files, rule_name)
    full_path = llm_dir / f"{rule_name}.llms-full.txt"
    full_path.write_text(full_content, encoding="utf-8")
