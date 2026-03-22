"""Markdown and YAML frontmatter generator for the Reddit Tool.

Converts a PRAW Submission and its collected comments into a structured
markdown file with machine-readable YAML frontmatter.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep_thought.reddit.config import RuleConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify_title(title: str, max_length: int = 60) -> str:
    """Convert a post title to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric characters with hyphens, collapses
    repeated hyphens, and strips leading/trailing hyphens.

    Args:
        title: The raw post title string.
        max_length: Maximum slug length before truncation.

    Returns:
        A cleaned slug suitable for use in a filename.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_length] if len(slug) > max_length else slug


def _get_author_name(obj: Any) -> str:
    """Extract the author username from a PRAW object safely.

    Args:
        obj: A PRAW Submission or Comment object with an author attribute.

    Returns:
        The author's username string, or "[deleted]" if the account is gone.
    """
    author = getattr(obj, "author", None)
    if author is None:
        return "[deleted]"
    return str(author)


def _format_date_from_utc(created_utc: float) -> str:
    """Format a Unix UTC timestamp as a YYYY-MM-DD date string.

    Args:
        created_utc: Unix timestamp from a PRAW object.

    Returns:
        ISO date string in YYYY-MM-DD format.
    """
    return datetime.fromtimestamp(created_utc, tz=UTC).strftime("%Y-%m-%d")


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
    submission: Any,
    rule_config: RuleConfig,
    word_count: int,
    processed_date: str,
) -> str:
    """Build the YAML frontmatter block for a post's markdown file.

    Args:
        submission: A PRAW Submission object.
        rule_config: The RuleConfig that collected this post.
        word_count: Word count of the full generated content.
        processed_date: ISO 8601 UTC timestamp string for when processing occurred.

    Returns:
        A string containing the full YAML frontmatter block including
        the opening and closing ``---`` delimiters and a trailing newline.
    """
    post_id = str(submission.id)
    subreddit_name = str(submission.subreddit.display_name)
    state_key = f"{post_id}:{subreddit_name}:{rule_config.name}"
    author_name = _get_author_name(submission)
    flair_text = submission.link_flair_text
    is_video = bool(getattr(submission, "is_video", False))

    # Escape title for YAML (quote it)
    escaped_title = str(submission.title).replace('"', '\\"')

    lines: list[str] = ["---"]
    lines.append("tool: reddit")
    lines.append(f"state_key: {state_key}")
    lines.append(f"post_id: {post_id}")
    lines.append(f"subreddit: {subreddit_name}")
    lines.append(f"rule: {rule_config.name}")
    lines.append(f'title: "{escaped_title}"')
    lines.append(f"author: u/{author_name}")
    lines.append(f"score: {submission.score}")
    lines.append(f"num_comments: {submission.num_comments}")
    lines.append(f"url: {submission.url}")
    lines.append(f"is_video: {str(is_video).lower()}")
    if flair_text is not None:
        lines.append(f'flair: "{flair_text}"')
    else:
        lines.append("flair: null")
    lines.append(f"word_count: {word_count}")
    lines.append(f"processed_date: {processed_date}")
    lines.append("---")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Comment rendering
# ---------------------------------------------------------------------------


def _render_comment(comment: Any, depth: int) -> str:
    """Render a single PRAW Comment as a markdown block at the given depth.

    Top-level comments (depth=0) use a ``###`` heading. Nested comments use
    blockquote indentation, with one ``>`` prefix per level of nesting.

    Args:
        comment: A PRAW Comment object.
        depth: Nesting depth (0 = top level, 1 = reply to top level, etc.).

    Returns:
        A rendered markdown string for the comment.
    """
    author_name = _get_author_name(comment)
    score = int(getattr(comment, "score", 0))
    body = str(getattr(comment, "body", "")).strip()

    if depth == 0:
        header = f"### u/{author_name} (\u2191 {score})"
        return f"{header}\n\n{body}"
    else:
        prefix = "> " * depth
        header_line = f"{prefix}**u/{author_name} (\u2191 {score})**"
        # Indent each line of the body with the blockquote prefix
        indented_body_lines = [f"{prefix}{line}" if line else prefix.rstrip() for line in body.splitlines()]
        indented_body = "\n".join(indented_body_lines)
        return f"{header_line}\n{prefix}\n{indented_body}"


def _get_comment_depth(comment: Any, submission: Any) -> int:
    """Calculate the nesting depth of a comment within a submission.

    Checks parent_id: if it starts with 't3_' the comment is top-level (depth 0),
    otherwise it is a reply (depth > 0). Because we have a flat list, we
    approximate depth by counting 't1_' chain length — but since we only need
    depth for display formatting, we use a simpler approach: check whether the
    parent is the submission (t3_) or another comment (t1_).

    Args:
        comment: A PRAW Comment object.
        submission: The parent PRAW Submission object.

    Returns:
        Integer depth; 0 for top-level comments.
    """
    parent_id = str(getattr(comment, "parent_id", ""))
    submission_fullname = f"t3_{submission.id}"
    if parent_id == submission_fullname:
        return 0
    return 1


def _render_comments_section(comments: list[Any], submission: Any) -> str:
    """Render all comments as a markdown section.

    Args:
        comments: Flat list of PRAW Comment objects (depth-first order).
        submission: The parent submission (used to detect top-level vs replies).

    Returns:
        A markdown string containing the full comments section, or an empty
        string if there are no comments.
    """
    if not comments:
        return ""

    rendered_blocks: list[str] = ["## Comments"]

    for comment in comments:
        depth = _get_comment_depth(comment, submission)
        rendered_block = _render_comment(comment, depth)
        rendered_blocks.append(rendered_block)

    return "\n\n".join(rendered_blocks)


# ---------------------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------------------


def _extract_image_url(submission: Any) -> str | None:
    """Extract an image URL from a submission if it links to a known image format.

    Args:
        submission: A PRAW Submission object.

    Returns:
        The image URL string if the submission links to an image, otherwise None.
    """
    url = str(submission.url)
    image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp")
    if any(url.lower().endswith(ext) for ext in image_extensions):
        return url
    # Reddit's image hosting
    if "i.redd.it" in url or "preview.redd.it" in url:
        return url
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_markdown(
    submission: Any,
    comments: list[Any],
    rule_config: RuleConfig,
) -> str:
    """Generate the full markdown content (frontmatter + body + comments) for a post.

    Args:
        submission: A PRAW Submission object.
        comments: Pre-fetched and flattened list of PRAW Comment objects.
        rule_config: The RuleConfig that collected this post.

    Returns:
        A complete markdown string ready to write to disk.
    """
    processed_date = datetime.now(tz=UTC).isoformat()

    # Build body section
    author_name = _get_author_name(submission)
    post_date = _format_date_from_utc(float(submission.created_utc))
    score_formatted = f"{submission.score:,}"

    header_line = (
        f"**Score:** {score_formatted} | "
        f"**Comments:** {submission.num_comments} | "
        f"**Posted:** {post_date} by u/{author_name}"
    )

    body_parts: list[str] = [
        f"# {submission.title}",
        "",
        header_line,
    ]

    selftext = str(submission.selftext).strip()
    if selftext and selftext != "[removed]" and selftext != "[deleted]":
        body_parts.extend(["", selftext])

    # Include image URL when configured
    if rule_config.include_images:
        image_url = _extract_image_url(submission)
        if image_url:
            body_parts.extend(["", f"![Image]({image_url})"])

    body_section = "\n".join(body_parts)

    # Build comments section
    comments_section = _render_comments_section(comments, submission)

    # Assemble full content without frontmatter (to count words first)
    full_body = f"{body_section}\n\n---\n\n{comments_section}" if comments_section else body_section

    word_count = count_words(full_body)

    # Build frontmatter with accurate word count
    frontmatter = _build_frontmatter(submission, rule_config, word_count, processed_date)

    return f"{frontmatter}\n{full_body}"


def write_post_file(
    content: str,
    output_dir: Path,
    rule_name: str,
    post_id: str,
    title: str,
) -> Path:
    """Write a post's markdown content to disk under the rule's output directory.

    File naming: ``{date}_{post_id}_{title_slug}.md``
    Directory: ``{output_dir}/{rule_name}/``

    Args:
        content: Full markdown content string to write.
        output_dir: Root output directory (e.g. data/reddit/export/).
        rule_name: The name of the rule, used as a subdirectory name.
        post_id: The Reddit post ID, included in the filename.
        title: The post title, slugified for the filename.

    Returns:
        The Path to the written markdown file.
    """
    rule_output_dir = output_dir / rule_name
    rule_output_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    title_slug = _slugify_title(title)
    filename = f"{date_prefix}_{post_id}_{title_slug}.md"

    output_path = rule_output_dir / filename
    output_path.write_text(content, encoding="utf-8")

    return output_path
