"""Local dataclasses for the Reddit Tool.

CollectedPostLocal mirrors the collected_posts database table and represents
the state of a single collected Reddit post, including its filtering outcome
and output file path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


def _get_author_name(submission: Any) -> str:
    """Extract the author username from a PRAW Submission safely.

    PRAW's author attribute is a Redditor object, or None for deleted accounts.

    Args:
        submission: A PRAW Submission object.

    Returns:
        The author's username string, or "[deleted]" if the account is gone.
    """
    author = submission.author
    if author is None:
        return "[deleted]"
    return str(author)


def _slugify_title(title: str) -> str:
    """Convert a post title to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric characters with hyphens, collapses
    repeated hyphens, and strips leading/trailing hyphens.

    Args:
        title: The raw post title string.

    Returns:
        A cleaned slug suitable for use in a filename.
    """
    import re

    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:80] if len(slug) > 80 else slug


# ---------------------------------------------------------------------------
# CollectedPostLocal
# ---------------------------------------------------------------------------


@dataclass
class CollectedPostLocal:
    """Local representation of a collected Reddit post.

    Mirrors the collected_posts database table. All timestamp fields are
    ISO 8601 strings. is_video uses SQLite integer convention: 1 = True, 0 = False.
    """

    state_key: str
    post_id: str
    subreddit: str
    rule_name: str
    title: str
    author: str
    score: int
    comment_count: int
    url: str
    is_video: int
    flair: str | None
    word_count: int
    output_path: str
    status: str
    created_at: str
    updated_at: str
    synced_at: str

    @classmethod
    def from_submission(
        cls,
        submission: Any,
        rule_name: str,
        output_path: str,
        word_count: int,
    ) -> CollectedPostLocal:
        """Convert a PRAW Submission object into a CollectedPostLocal.

        Builds the composite state_key from the post_id, subreddit name, and
        rule_name. Timestamps are set to the current UTC time.

        Args:
            submission: A PRAW Submission object.
            rule_name: The name of the rule that triggered collection of this post.
            output_path: Path to the generated markdown file on disk.
            word_count: Word count of the generated markdown content.

        Returns:
            A CollectedPostLocal with all fields populated.
        """
        post_id: str = str(submission.id)
        subreddit_name: str = str(submission.subreddit.display_name)
        state_key: str = f"{post_id}:{subreddit_name}:{rule_name}"
        author_name: str = _get_author_name(submission)
        flair_text: str | None = submission.link_flair_text

        is_video_flag: int = 1 if getattr(submission, "is_video", False) else 0

        current_timestamp: str = datetime.now(tz=UTC).isoformat()

        return cls(
            state_key=state_key,
            post_id=post_id,
            subreddit=subreddit_name,
            rule_name=rule_name,
            title=str(submission.title),
            author=author_name,
            score=int(submission.score),
            comment_count=int(submission.num_comments),
            url=str(submission.url),
            is_video=is_video_flag,
            flair=flair_text,
            word_count=word_count,
            output_path=output_path,
            status="ok",
            created_at=current_timestamp,
            updated_at=current_timestamp,
            synced_at=current_timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by database column names.

        Returns:
            A plain dictionary representation of this dataclass suitable
            for passing to database query functions.
        """
        return asdict(self)
