"""Local dataclasses for the Reddit Tool.

CollectedPostLocal mirrors the collected_posts database table and represents
the state of a single collected Reddit post, including its filtering outcome
and output file path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from deep_thought.reddit.utils import get_author_name, slugify_title  # noqa: F401 — re-exported for callers

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
    upvote_ratio: float
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
        author_name: str = get_author_name(submission.author)
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
            upvote_ratio=float(getattr(submission, "upvote_ratio", 0.0)),
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
