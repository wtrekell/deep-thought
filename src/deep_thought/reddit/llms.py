"""LLM context file generator for the Reddit Tool.

Produces two aggregate files per rule from collected posts:
- llms.txt: a navigable index with one entry per post
- llms-full.txt: complete markdown content of every post, concatenated

These files are intended to be loaded by LLMs as context. The format
prioritises machine parseability over human readability.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep_thought.reddit.models import CollectedPostLocal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_frontmatter(markdown_text: str) -> str:
    """Remove YAML frontmatter from a markdown string.

    Frontmatter is defined as content between the first two ``---`` lines
    at the very beginning of the file. If no valid frontmatter block is
    found the text is returned unchanged.

    Args:
        markdown_text: Full markdown content, possibly starting with ``---``.

    Returns:
        The markdown body with the frontmatter block removed.
    """
    lines = markdown_text.splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown_text

    closing_index: int | None = None
    for line_index in range(1, len(lines)):
        if lines[line_index].strip() == "---":
            closing_index = line_index
            break

    if closing_index is None:
        return markdown_text

    body_lines = lines[closing_index + 1 :]
    return "\n".join(body_lines).lstrip("\n")


def _slugify_title(title: str, max_length: int = 60) -> str:
    """Convert a post title to a filesystem-safe slug.

    Args:
        title: The raw post title string.
        max_length: Maximum slug length before truncation.

    Returns:
        A cleaned slug suitable for use in a link.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_length] if len(slug) > max_length else slug


def _read_post_content(post: CollectedPostLocal) -> str:
    """Read and return the markdown content of a post's output file.

    Args:
        post: A CollectedPostLocal with a valid output_path.

    Returns:
        The file content as a string, or an empty string if the file is missing.
    """
    output_file_path = Path(post.output_path)
    if not output_file_path.exists():
        return ""
    return output_file_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_llms_index(posts: list[CollectedPostLocal], rule_name: str) -> str:
    """Generate llms.txt index content for all posts collected under a rule.

    Follows the llmstxt.org convention: one line per post with a link,
    subreddit, score, and word count.

    Args:
        posts: List of CollectedPostLocal objects for this rule.
        rule_name: The name of the rule, used in the index header.

    Returns:
        The full llms.txt content as a string.
    """
    collected_date = datetime.now(tz=UTC).date().isoformat()
    post_count = len(posts)

    lines: list[str] = [
        f"# Post Index — {rule_name}",
        "",
        f"> Collected by reddit on {collected_date}. {post_count} posts.",
        "",
        "## Posts",
        "",
    ]

    for post in posts:
        title_slug = _slugify_title(post.title)
        output_filename = Path(post.output_path).name
        relative_path = f"{rule_name}/{output_filename}"
        entry = f"- [{title_slug}.md]({relative_path}): r/{post.subreddit}, score {post.score}, {post.word_count} words"
        lines.append(entry)

    return "\n".join(lines)


def generate_llms_full(posts: list[CollectedPostLocal], rule_name: str) -> str:
    """Generate llms-full.txt aggregate content for all posts collected under a rule.

    Each post is written as a block separated by a ``---`` divider. The post
    body has its YAML frontmatter stripped so only the content is included.

    Args:
        posts: List of CollectedPostLocal objects for this rule.
        rule_name: The name of the rule, included in each post's metadata block.

    Returns:
        The full llms-full.txt content as a string.
    """
    collected_date = datetime.now(tz=UTC).isoformat()
    blocks: list[str] = []

    for post in posts:
        raw_content = _read_post_content(post)
        stripped_content = _strip_frontmatter(raw_content)

        block_lines: list[str] = [
            f"# {post.title}",
            "",
            f"post_id: {post.post_id}",
            f"subreddit: {post.subreddit}",
            f"rule: {rule_name}",
            f"score: {post.score}",
            f"comments: {post.comment_count}",
            f"collected: {collected_date}",
            "",
            stripped_content,
            "",
            "---",
        ]
        blocks.append("\n".join(block_lines))

    return "\n".join(blocks)


def write_llms_files(
    posts: list[CollectedPostLocal],
    output_dir: Path,
    rule_name: str,
) -> tuple[Path, Path]:
    """Write both llms.txt and llms-full.txt to the rule's output directory.

    Args:
        posts: List of CollectedPostLocal objects for this rule.
        output_dir: Root output directory (e.g. data/reddit/export/).
        rule_name: The name of the rule; files are written to output_dir/rule_name/.

    Returns:
        A tuple of (llms_txt_path, llms_full_txt_path).
    """
    rule_output_dir = output_dir / rule_name
    rule_output_dir.mkdir(parents=True, exist_ok=True)

    llms_index_content = generate_llms_index(posts, rule_name)
    llms_full_content = generate_llms_full(posts, rule_name)

    llms_txt_path = rule_output_dir / "llms.txt"
    llms_full_txt_path = rule_output_dir / "llms-full.txt"

    llms_txt_path.write_text(llms_index_content, encoding="utf-8")
    llms_full_txt_path.write_text(llms_full_content, encoding="utf-8")

    return llms_txt_path, llms_full_txt_path


def write_post_llms_files(
    post_content: str,
    output_dir: Path,
    rule_name: str,
    post_id: str,
    title: str,
    post_metadata: Any,
) -> None:
    """Write per-post llms.txt and llms-full.txt sidecar files.

    These are lightweight per-post index files stored in an ``llm/``
    subdirectory alongside the main post markdown file.

    Args:
        post_content: Full markdown content of the post (with frontmatter).
        output_dir: Root output directory.
        rule_name: Rule name for the subdirectory path.
        post_id: Reddit post ID for the filename.
        title: Post title for the filename slug.
        post_metadata: CollectedPostLocal or similar object with score/comment_count.
    """
    from deep_thought.reddit.output import _slugify_title  # noqa: PLC0415

    llm_dir = output_dir / rule_name / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    title_slug = _slugify_title(title)
    base_name = f"{date_prefix}_{post_id}_{title_slug}"

    stripped_content = _strip_frontmatter(post_content)
    collected_date = datetime.now(tz=UTC).isoformat()

    # llms.txt (index-style)
    llms_index_lines: list[str] = [
        f"# {title}",
        "",
        f"> Collected by reddit on {collected_date}.",
        "",
        f"- [{base_name}.md](../{base_name}.md)",
    ]
    llms_txt_path = llm_dir / f"{base_name}.llms.txt"
    llms_txt_path.write_text("\n".join(llms_index_lines), encoding="utf-8")

    # llms-full.txt (full content)
    llms_full_lines: list[str] = [
        f"# {title}",
        "",
        f"post_id: {post_id}",
        f"rule: {rule_name}",
        f"collected: {collected_date}",
        "",
        stripped_content,
    ]
    llms_full_path = llm_dir / f"{base_name}.llms-full.txt"
    llms_full_path.write_text("\n".join(llms_full_lines), encoding="utf-8")
