"""Markdown output generation for the Gmail Tool.

Generates markdown files with YAML frontmatter from collected emails.
Supports both per-email files and append mode (all emails for a rule
accumulate in one file).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deep_thought.gmail.models import _extract_header
from deep_thought.text_utils import slugify as _shared_slugify

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Frontmatter generation
# ---------------------------------------------------------------------------


def _build_frontmatter(
    message: dict[str, Any],
    rule_name: str,
    actions: list[str],
) -> str:
    """Build YAML frontmatter from message metadata.

    Only includes fields with non-null, non-empty values.

    Args:
        message: A Gmail API message dict.
        rule_name: The name of the collection rule.
        actions: List of action strings that were applied.

    Returns:
        A YAML frontmatter string including the --- delimiters.
    """
    lines = ["---"]
    lines.append("tool: gmail")

    message_id = message.get("id", "")
    if message_id:
        lines.append(f"message_id: {message_id}")

    lines.append(f"rule: {rule_name}")

    from_header = _extract_header(message, "From")
    if from_header:
        escaped_from = from_header.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'from: "{escaped_from}"')

    subject = _extract_header(message, "Subject")
    if subject:
        escaped_subject = subject.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'subject: "{escaped_subject}"')

    date_header = _extract_header(message, "Date")
    if date_header:
        escaped_date = date_header.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'date: "{escaped_date}"')

    if actions:
        lines.append("actions_taken:")
        for action in actions:
            lines.append(f"  - {action}")

    processed_date = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"processed_date: {processed_date}")

    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Body text extraction
# ---------------------------------------------------------------------------


def extract_body_text(message: dict[str, Any]) -> tuple[str, str | None]:
    """Extract plain text and HTML body from a Gmail API message.

    Traverses the payload structure to find text/plain and text/html parts.

    Args:
        message: A Gmail API message dict (format='full').

    Returns:
        A tuple of (plain_text, html_text). Either may be empty string or None.
    """
    import base64

    payload = message.get("payload", {})
    plain_text = ""
    html_text: str | None = None

    def _extract_from_part(part: dict[str, Any]) -> None:
        nonlocal plain_text, html_text

        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data", "")

        if mime_type == "text/plain" and data and not plain_text:
            plain_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        elif mime_type == "text/html" and data and html_text is None:
            html_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        for sub_part in part.get("parts", []):
            _extract_from_part(sub_part)

    _extract_from_part(payload)
    return plain_text, html_text


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def generate_email_markdown(
    message: dict[str, Any],
    body_text: str,
    rule_name: str,
    actions: list[str],
) -> str:
    """Generate a complete markdown document for a single email.

    Args:
        message: A Gmail API message dict.
        body_text: The cleaned email body text (plain text or cleaned HTML).
        rule_name: The name of the collection rule.
        actions: List of action strings that were applied.

    Returns:
        A complete markdown string with YAML frontmatter and body.
    """
    frontmatter = _build_frontmatter(message, rule_name, actions)
    return f"{frontmatter}\n\n{body_text}\n"


def write_email_file(
    content: str,
    output_dir: Path,
    rule_name: str,
    subject: str,
    date_str: str,
) -> Path:
    """Write a single email's markdown content to a file.

    Creates the rule subdirectory if it does not exist. The filename is
    built from the date and a slugified subject. If a file with the same
    name already exists (e.g., two subjects that truncate identically at
    80 characters), a counter suffix (_1, _2, ...) is appended before the
    .md extension to avoid overwriting.

    Args:
        content: The full markdown content to write.
        output_dir: The root output directory.
        rule_name: The rule name (used as subdirectory).
        subject: The email subject (slugified for the filename).
        date_str: A date string for the filename prefix (YYMMDD).

    Returns:
        The Path to the written file.
    """
    subject_slug = _shared_slugify(subject)
    base_stem = f"{date_str}-{subject_slug}" if subject_slug else f"{date_str}-no-subject"

    rule_dir = output_dir / rule_name
    rule_dir.mkdir(parents=True, exist_ok=True)

    # Resolve filename collisions by appending a counter suffix
    file_path = rule_dir / f"{base_stem}.md"
    collision_counter = 1
    while file_path.exists():
        file_path = rule_dir / f"{base_stem}_{collision_counter}.md"
        collision_counter += 1

    file_path.write_text(content, encoding="utf-8")
    return file_path


def append_to_rule_file(
    content: str,
    output_dir: Path,
    rule_name: str,
) -> Path:
    """Append email content to the aggregate file for a rule.

    In append mode, all emails for a rule accumulate in a single file
    at {output_dir}/{rule_name}/{rule_name}.md. New entries are separated
    by a horizontal rule.

    Args:
        content: The full markdown content to append (including frontmatter).
        output_dir: The root output directory.
        rule_name: The rule name (used as subdirectory and filename).

    Returns:
        The Path to the aggregate file.
    """
    rule_dir = output_dir / rule_name
    rule_dir.mkdir(parents=True, exist_ok=True)

    file_path = rule_dir / f"{rule_name}.md"

    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")
        combined = f"{existing}\n\n---\n\n{content}"
        file_path.write_text(combined, encoding="utf-8")
    else:
        file_path.write_text(content, encoding="utf-8")

    return file_path


def append_raw_to_rule_file(
    content: str,
    output_dir: Path,
    rule_name: str,
) -> Path | None:
    """Append bare content to a line-oriented aggregate file for a rule.

    Intended for chaining the Gmail tool's AI-extracted output into other
    deep-thought tools (for example, a URL list consumed by
    ``web crawl --mode direct --input-file``). Unlike ``append_to_rule_file``,
    no YAML frontmatter, markdown heading, or horizontal-rule separator is
    written, and the file extension is ``.txt`` to signal that the payload is
    not markdown.

    Lines are deduplicated across the full file contents after concatenation,
    preserving first-seen order. Empty or whitespace-only input is a no-op
    (no file is created or modified) and the function returns ``None`` so the
    caller can decide not to record an output path.

    Args:
        content: The bare text to append. Typically the AI extractor's output.
        output_dir: The root output directory.
        rule_name: The rule name (used as subdirectory and filename stem).

    Returns:
        The Path to the aggregate file when content was written, or ``None``
        if the input was empty after stripping whitespace.
    """
    if not content.strip():
        return None

    rule_dir = output_dir / rule_name
    rule_dir.mkdir(parents=True, exist_ok=True)

    file_path = rule_dir / f"{rule_name}.txt"

    existing = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    combined_lines = existing.splitlines() + content.splitlines()

    seen: dict[str, None] = {}
    for line in combined_lines:
        if line not in seen:
            seen[line] = None

    final = "\n".join(seen.keys())
    if final:
        final += "\n"

    file_path.write_text(final, encoding="utf-8")
    return file_path
