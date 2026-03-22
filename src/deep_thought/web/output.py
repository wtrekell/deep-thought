"""Page output writer for the web crawl tool.

Generates output markdown files with YAML frontmatter from crawled page
content. Each page is written to a path derived from its URL structure
within the output root directory.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Path and slug helpers
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    """Convert a string to a URL-safe slug.

    Lowercases the text, replaces non-alphanumeric characters with hyphens,
    collapses consecutive hyphens into one, and strips leading/trailing hyphens.
    Truncates to 100 characters.

    Args:
        text: The input string to slugify.

    Returns:
        A slug string of at most 100 characters.
    """
    lowercased = text.lower()
    non_alnum_replaced = re.sub(r"[^a-z0-9]+", "-", lowercased)
    collapsed_hyphens = re.sub(r"-{2,}", "-", non_alnum_replaced)
    stripped = collapsed_hyphens.strip("-")
    return stripped[:100]


def url_to_output_path(url: str, output_root: Path) -> Path:
    """Derive an output file path from a URL.

    The URL's domain becomes the first directory; the URL's path segments
    become subdirectories. The final filename is the slugified last path
    segment (or 'index' if the path is empty or root-only).

    Example:
        ``https://example.com/blog/my-post``
        → ``output_root/example.com/blog/my-post.md``

    Args:
        url: The source URL to derive a path from.
        output_root: The root directory under which all output files are written.

    Returns:
        The target output Path, including the .md extension.
    """
    parsed = urlparse(url)
    domain = parsed.netloc or "unknown"

    raw_path = parsed.path.strip("/")
    path_parts = [part for part in raw_path.split("/") if part]

    if not path_parts:
        filename_slug = "index"
        directory_parts: list[str] = []
    else:
        last_segment = path_parts[-1]
        filename_slug = slugify(last_segment) or "index"
        directory_parts = path_parts[:-1]

    output_path = output_root / domain
    for directory_segment in directory_parts:
        output_path = output_path / directory_segment

    return output_path / f"{filename_slug}.md"


# ---------------------------------------------------------------------------
# Frontmatter builder
# ---------------------------------------------------------------------------


def _build_frontmatter(url: str, mode: str, title: str | None, word_count: int) -> str:
    """Build a YAML frontmatter block string.

    The processed_date field is set to the current UTC time. The title field
    is omitted when None.

    Args:
        url: The source URL of the crawled page.
        mode: The crawl mode used (e.g., 'blog', 'documentation', 'direct').
        title: The page title, or None to omit the field.
        word_count: Approximate word count of the converted markdown body.

    Returns:
        A string containing the full YAML frontmatter block including
        the opening and closing ``---`` delimiters and a trailing newline.
    """
    processed_date = datetime.now(tz=UTC).isoformat()

    lines: list[str] = ["---"]
    lines.append("tool: web")
    lines.append(f"url: {url}")
    lines.append(f"mode: {mode}")
    if title is not None:
        lines.append(f"title: {title}")
    lines.append(f"word_count: {word_count}")
    lines.append(f"processed_date: {processed_date}")
    lines.append("---")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_page(
    markdown_text: str,
    url: str,
    mode: str,
    title: str | None,
    word_count: int,
    output_root: Path,
) -> Path:
    """Write a crawled page's markdown to disk with YAML frontmatter.

    Creates parent directories as needed. The output path is derived from
    the URL using url_to_output_path.

    Args:
        markdown_text: The converted markdown body of the page.
        url: The source URL of the crawled page.
        mode: The crawl mode used (e.g., 'blog', 'documentation', 'direct').
        title: The page title, or None if not available.
        word_count: Approximate word count of markdown_text.
        output_root: Root directory under which per-page files are written.

    Returns:
        The Path to the written markdown file.
    """
    output_file_path = url_to_output_path(url, output_root)
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter_block = _build_frontmatter(url=url, mode=mode, title=title, word_count=word_count)
    full_content = frontmatter_block + "\n" + markdown_text

    output_file_path.write_text(full_content, encoding="utf-8")
    return output_file_path
