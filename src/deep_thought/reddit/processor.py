"""Rule engine and orchestration for the Reddit Tool.

Coordinates fetching submissions, applying filters, generating output files,
and writing state to the database. Handles per-post errors gracefully —
one failing post never aborts the rest of the collection run.
"""

from __future__ import annotations

import logging
import sqlite3  # noqa: TC003
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deep_thought.progress import track_items
from deep_thought.reddit.filters import apply_rule_filters
from deep_thought.reddit.models import CollectedPostLocal
from deep_thought.reddit.output import count_words, generate_markdown, write_post_file

if TYPE_CHECKING:
    from deep_thought.reddit.client import RedditClient
    from deep_thought.reddit.config import RedditConfig, RuleConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CollectionResult:
    """Summary of a collection run (one or more rules)."""

    posts_collected: int = 0
    posts_skipped: int = 0
    posts_updated: int = 0
    posts_errored: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_output_path(
    output_dir: Path,
    rule_name: str,
    post_id: str,
    title: str,
) -> str:
    """Compute the expected output file path for a post (without writing it).

    Used to calculate the path before generating markdown, so it can be stored
    in the database even in dry-run mode.

    Args:
        output_dir: Root output directory.
        rule_name: Rule name subdirectory.
        post_id: Reddit post ID for the filename.
        title: Post title to slugify for the filename.

    Returns:
        String representation of the output file path.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from deep_thought.reddit.utils import slugify_title  # noqa: PLC0415

    date_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    title_slug = slugify_title(title)
    filename = f"{date_prefix}_{post_id}_{title_slug}.md"
    return str(output_dir / rule_name / filename)


def _process_single_post(
    submission: Any,
    rule_config: RuleConfig,
    reddit_client: RedditClient,
    db_conn: sqlite3.Connection,
    output_dir: Path,
    *,
    dry_run: bool,
    force: bool,
) -> tuple[str, bool]:
    """Fetch comments, generate markdown, write output, and upsert the database record.

    Args:
        submission: A PRAW Submission object.
        rule_config: The RuleConfig governing this collection.
        reddit_client: The RedditClient for fetching comments.
        db_conn: An open SQLite connection.
        output_dir: Root output directory for markdown files.
        dry_run: If True, skip all writes.
        force: If True, reprocess even if the post already exists in the DB.

    Returns:
        A tuple of (action, updated) where action is 'collected', 'updated',
        or 'skipped', and updated is True if this was an update to an existing post.

    Raises:
        Exception: Propagated from PRAW or file I/O; callers must handle.
    """
    from deep_thought.reddit.db.queries import get_collected_post, upsert_collected_post  # noqa: PLC0415

    post_id = str(submission.id)
    subreddit_name = str(submission.subreddit.display_name)
    state_key = f"{post_id}:{subreddit_name}:{rule_config.name}"

    existing_row = get_collected_post(db_conn, state_key)

    if existing_row is not None and not force:
        # Incremental update: re-check comment count
        stored_comment_count = int(existing_row["comment_count"])
        live_comment_count = int(submission.num_comments)
        if live_comment_count <= stored_comment_count:
            logger.debug("Post %s unchanged (comments: %d), skipping.", state_key, stored_comment_count)
            return "skipped", False
        logger.debug(
            "Post %s has new comments (%d -> %d), updating.",
            state_key,
            stored_comment_count,
            live_comment_count,
        )

    # Fetch comments
    comments = reddit_client.get_comments(
        submission,
        max_depth=rule_config.max_comment_depth,
        max_comments=rule_config.max_comments,
    )

    # Generate markdown
    markdown_content = generate_markdown(submission, comments, rule_config)
    word_count = count_words(markdown_content)

    output_path_str = _build_output_path(output_dir, rule_config.name, post_id, str(submission.title))

    if not dry_run:
        written_path = write_post_file(
            content=markdown_content,
            output_dir=output_dir,
            rule_name=rule_config.name,
            post_id=post_id,
            title=str(submission.title),
        )
        output_path_str = str(written_path)

        local_post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name=rule_config.name,
            output_path=output_path_str,
            word_count=word_count,
        )
        upsert_collected_post(db_conn, local_post.to_dict())

    is_update = existing_row is not None
    return ("updated" if is_update else "collected"), is_update


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def process_rule(
    reddit_client: RedditClient,
    rule_config: RuleConfig,
    db_conn: sqlite3.Connection,
    output_dir: Path,
    *,
    dry_run: bool,
    force: bool,
    global_post_count: int,
    max_posts_per_run: int,
) -> CollectionResult:
    """Fetch submissions for a single rule, apply filters, and process each post.

    Stops early when the global post cap is reached. Per-post exceptions are
    caught, logged, and counted — the remaining posts continue processing.

    Args:
        reddit_client: The RedditClient wrapping PRAW.
        rule_config: The RuleConfig governing this rule's collection.
        db_conn: An open SQLite connection for reading/writing state.
        output_dir: Root directory for markdown output files.
        dry_run: If True, log what would happen without writing anything.
        force: If True, ignore existing state and reprocess all posts.
        global_post_count: Number of posts already collected in this run (across all rules).
        max_posts_per_run: Hard cap on total posts collected per invocation.

    Returns:
        A CollectionResult summarising this rule's outcome.
    """
    result = CollectionResult()

    if global_post_count >= max_posts_per_run:
        logger.info("Global post cap (%d) reached before rule '%s'.", max_posts_per_run, rule_config.name)
        return result

    logger.info("Processing rule '%s' (subreddit: r/%s).", rule_config.name, rule_config.subreddit)

    try:
        submissions = reddit_client.get_submissions(
            subreddit=rule_config.subreddit,
            sort=rule_config.sort,
            time_filter=rule_config.time_filter,
            limit=rule_config.limit,
        )
    except Exception as fetch_error:
        error_message = f"Failed to fetch submissions for rule '{rule_config.name}': {fetch_error}"
        logger.error(error_message)
        result.errors.append(error_message)
        result.posts_errored += 1
        return result

    for submission in track_items(submissions, description=f"Rule: {rule_config.name}", total=rule_config.limit):
        remaining_capacity = max_posts_per_run - global_post_count - result.posts_collected - result.posts_updated
        if remaining_capacity <= 0:
            logger.info("Global post cap reached during rule '%s'.", rule_config.name)
            break

        try:
            # For keyword filtering with search_comments, we need comments up-front
            pre_fetch_comments: list[Any] | None = None
            if rule_config.search_comments and (rule_config.include_keywords or rule_config.exclude_keywords):
                pre_fetch_comments = reddit_client.get_comments(
                    submission,
                    max_depth=rule_config.max_comment_depth,
                    max_comments=rule_config.max_comments,
                )

            if not apply_rule_filters(submission, rule_config, pre_fetch_comments):
                result.posts_skipped += 1
                continue

            action, is_update = _process_single_post(
                submission=submission,
                rule_config=rule_config,
                reddit_client=reddit_client,
                db_conn=db_conn,
                output_dir=output_dir,
                dry_run=dry_run,
                force=force,
            )

            if action == "skipped":
                result.posts_skipped += 1
            elif action == "updated":
                result.posts_updated += 1
                logger.debug("Updated post %s.", submission.id)
            else:
                result.posts_collected += 1
                logger.debug("Collected post %s.", submission.id)

        except Exception as post_error:
            state_key = f"{submission.id}:{submission.subreddit.display_name}:{rule_config.name}"
            error_message = f"Error processing post {state_key}: {post_error}"
            logger.error(error_message)
            result.errors.append(error_message)
            result.posts_errored += 1

    return result


def run_collection(
    reddit_client: RedditClient,
    config: RedditConfig,
    db_conn: sqlite3.Connection,
    *,
    dry_run: bool,
    force: bool,
    rule_name_filter: str | None,
    output_override: Path | None,
) -> CollectionResult:
    """Run the full collection cycle across all configured rules.

    Applies an optional rule name filter to run only a specific rule.
    Accumulates results across all rules into a single CollectionResult.

    Args:
        reddit_client: The RedditClient wrapping PRAW.
        config: The loaded RedditConfig with all rules and global settings.
        db_conn: An open SQLite connection for reading/writing state.
        dry_run: If True, no writes are made to disk or the database.
        force: If True, ignore existing state and reprocess all posts.
        rule_name_filter: If set, only the rule with this name is processed.
        output_override: If set, use this directory instead of config.output_dir.

    Returns:
        A CollectionResult aggregating counts and errors from all rules.
    """
    aggregate_result = CollectionResult()

    output_dir = output_override if output_override is not None else Path(config.output_dir)

    rules_to_run = config.rules
    if rule_name_filter is not None:
        rules_to_run = [rule for rule in config.rules if rule.name == rule_name_filter]
        if not rules_to_run:
            aggregate_result.errors.append(
                f"No rule named '{rule_name_filter}' found in configuration. "
                f"Available rules: {[r.name for r in config.rules]}"
            )
            return aggregate_result

    global_post_count = 0

    for rule_config in track_items(rules_to_run, description="Processing rules"):
        rule_result = process_rule(
            reddit_client=reddit_client,
            rule_config=rule_config,
            db_conn=db_conn,
            output_dir=output_dir,
            dry_run=dry_run,
            force=force,
            global_post_count=global_post_count,
            max_posts_per_run=config.max_posts_per_run,
        )

        aggregate_result.posts_collected += rule_result.posts_collected
        aggregate_result.posts_skipped += rule_result.posts_skipped
        aggregate_result.posts_updated += rule_result.posts_updated
        aggregate_result.posts_errored += rule_result.posts_errored
        aggregate_result.errors.extend(rule_result.errors)

        global_post_count += rule_result.posts_collected + rule_result.posts_updated

    return aggregate_result
