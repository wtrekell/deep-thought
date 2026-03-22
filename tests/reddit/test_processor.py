"""Tests for collection orchestration in deep_thought.reddit.processor.

Tests cover rule processing, incremental update detection, force mode,
global post caps, and per-post error handling.
"""

from __future__ import annotations

import sqlite3  # noqa: TC003
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

import pytest

from deep_thought.reddit.config import RedditConfig, RuleConfig
from deep_thought.reddit.processor import CollectionResult, process_rule, run_collection
from tests.reddit.conftest import make_mock_submission

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule_config(
    name: str = "test_rule",
    subreddit: str = "python",
    min_score: int = 0,
    min_comments: int = 0,
    max_age_days: int = 30,
) -> RuleConfig:
    """Build a permissive RuleConfig for processor tests."""
    return RuleConfig(
        name=name,
        subreddit=subreddit,
        sort="top",
        time_filter="week",
        limit=10,
        min_score=min_score,
        min_comments=min_comments,
        max_age_days=max_age_days,
        include_keywords=[],
        exclude_keywords=[],
        include_flair=[],
        exclude_flair=[],
        search_comments=False,
        max_comment_depth=2,
        max_comments=50,
        include_images=False,
    )


def _make_reddit_config(rules: list[RuleConfig] | None = None) -> RedditConfig:
    """Build a minimal RedditConfig for processor tests."""
    return RedditConfig(
        client_id_env="REDDIT_CLIENT_ID",
        client_secret_env="REDDIT_CLIENT_SECRET",
        user_agent_env="REDDIT_USER_AGENT",
        max_posts_per_run=100,
        output_dir="data/reddit/export/",
        generate_llms_files=False,
        rules=rules or [_make_rule_config()],
    )


# ---------------------------------------------------------------------------
# CollectionResult dataclass
# ---------------------------------------------------------------------------


class TestCollectionResult:
    def test_default_values_are_zero(self) -> None:
        """A freshly created CollectionResult should have all counts at zero."""
        result = CollectionResult()
        assert result.posts_collected == 0
        assert result.posts_skipped == 0
        assert result.posts_updated == 0
        assert result.posts_errored == 0
        assert result.errors == []


# ---------------------------------------------------------------------------
# process_rule — submission fetch failure
# ---------------------------------------------------------------------------


class TestProcessRuleSubmissionFetchFailure:
    @pytest.mark.error_handling
    def test_returns_error_result_when_submissions_fetch_fails(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When get_submissions raises, the result should contain the error."""
        mock_client = MagicMock()
        mock_client.get_submissions.side_effect = RuntimeError("API error")
        rule_config = _make_rule_config()

        result = process_rule(
            reddit_client=mock_client,
            rule_config=rule_config,
            db_conn=in_memory_db,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            global_post_count=0,
            max_posts_per_run=100,
        )

        assert result.posts_errored == 1
        assert len(result.errors) == 1
        assert "API error" in result.errors[0]


# ---------------------------------------------------------------------------
# process_rule — global cap enforcement
# ---------------------------------------------------------------------------


class TestProcessRuleGlobalCap:
    def test_returns_empty_result_when_global_cap_already_reached(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When global_post_count >= max_posts_per_run, no processing should occur."""
        mock_client = MagicMock()
        rule_config = _make_rule_config()

        result = process_rule(
            reddit_client=mock_client,
            rule_config=rule_config,
            db_conn=in_memory_db,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            global_post_count=100,
            max_posts_per_run=100,
        )

        mock_client.get_submissions.assert_not_called()
        assert result.posts_collected == 0


# ---------------------------------------------------------------------------
# process_rule — dry_run
# ---------------------------------------------------------------------------


class TestProcessRuleDryRun:
    def test_dry_run_does_not_write_files(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """In dry_run mode, no markdown files should be written to disk."""
        submission = make_mock_submission(score=100, num_comments=10)
        mock_client = MagicMock()
        mock_client.get_submissions.return_value = [submission]
        mock_client.get_comments.return_value = []
        rule_config = _make_rule_config()

        with (
            patch("deep_thought.reddit.processor.apply_rule_filters", return_value=True),
            patch("deep_thought.reddit.db.queries.get_collected_post", return_value=None),
            patch("deep_thought.reddit.processor.generate_markdown", return_value="# content"),
        ):
            process_rule(
                reddit_client=mock_client,
                rule_config=rule_config,
                db_conn=in_memory_db,
                output_dir=tmp_path,
                dry_run=True,
                force=False,
                global_post_count=0,
                max_posts_per_run=100,
            )

        # No files should have been written
        rule_dir = tmp_path / "test_rule"
        assert not rule_dir.exists() or not any(rule_dir.iterdir())


# ---------------------------------------------------------------------------
# process_rule — filter skip
# ---------------------------------------------------------------------------


class TestProcessRuleFilterSkip:
    def test_post_filtered_out_is_counted_as_skipped(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """Posts that fail rule filters should be counted in posts_skipped."""
        submission = make_mock_submission(score=1)  # Below any reasonable min_score
        mock_client = MagicMock()
        mock_client.get_submissions.return_value = [submission]
        rule_config = _make_rule_config(min_score=9999)

        result = process_rule(
            reddit_client=mock_client,
            rule_config=rule_config,
            db_conn=in_memory_db,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            global_post_count=0,
            max_posts_per_run=100,
        )

        assert result.posts_skipped >= 1
        assert result.posts_collected == 0


# ---------------------------------------------------------------------------
# process_rule — per-post error handling
# ---------------------------------------------------------------------------


class TestProcessRulePerPostError:
    @pytest.mark.error_handling
    def test_per_post_error_is_logged_and_collection_continues(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """A per-post error should be counted and collection should continue with other posts."""
        submission_good = make_mock_submission(post_id="good1", score=100, num_comments=10)
        submission_bad = make_mock_submission(post_id="bad1", score=100, num_comments=10)
        mock_client = MagicMock()
        mock_client.get_submissions.return_value = [submission_bad, submission_good]
        mock_client.get_comments.return_value = []
        rule_config = _make_rule_config()

        call_count = 0

        def patched_generate(submission: object, comments: object, rule: object) -> str:
            nonlocal call_count
            call_count += 1
            if submission is submission_bad:
                raise RuntimeError("Generation failed")
            return "# good content"

        with (
            patch("deep_thought.reddit.processor.apply_rule_filters", return_value=True),
            patch("deep_thought.reddit.db.queries.get_collected_post", return_value=None),
            patch("deep_thought.reddit.processor.generate_markdown", side_effect=patched_generate),
            patch("deep_thought.reddit.processor.write_post_file", return_value=tmp_path / "out.md"),
            patch("deep_thought.reddit.db.queries.upsert_collected_post"),
        ):
            result = process_rule(
                reddit_client=mock_client,
                rule_config=rule_config,
                db_conn=in_memory_db,
                output_dir=tmp_path,
                dry_run=False,
                force=False,
                global_post_count=0,
                max_posts_per_run=100,
            )

        assert result.posts_errored == 1
        assert result.posts_collected == 1
        assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# run_collection — rule name filter
# ---------------------------------------------------------------------------


class TestRunCollectionRuleFilter:
    def test_unknown_rule_name_returns_error(self, in_memory_db: sqlite3.Connection) -> None:
        """Passing a rule_name_filter that matches no rules should produce an error."""
        mock_client = MagicMock()
        config = _make_reddit_config()

        result = run_collection(
            reddit_client=mock_client,
            config=config,
            db_conn=in_memory_db,
            dry_run=False,
            force=False,
            rule_name_filter="nonexistent_rule",
            output_override=None,
        )

        assert len(result.errors) == 1
        assert "nonexistent_rule" in result.errors[0]
        mock_client.get_submissions.assert_not_called()

    def test_specific_rule_filter_runs_only_that_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """When rule_name_filter is set, only the matching rule should be processed."""
        mock_client = MagicMock()
        mock_client.get_submissions.return_value = []

        rule_a = _make_rule_config(name="rule_a")
        rule_b = _make_rule_config(name="rule_b")
        config = _make_reddit_config(rules=[rule_a, rule_b])

        run_collection(
            reddit_client=mock_client,
            config=config,
            db_conn=in_memory_db,
            dry_run=False,
            force=False,
            rule_name_filter="rule_a",
            output_override=None,
        )

        # get_submissions should only be called once (for rule_a)
        assert mock_client.get_submissions.call_count == 1
        call_kwargs = mock_client.get_submissions.call_args
        assert call_kwargs.kwargs.get("subreddit") == "python"

    def test_output_override_is_used_instead_of_config_dir(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When output_override is provided, it should be used as the output directory."""
        mock_client = MagicMock()
        mock_client.get_submissions.return_value = []
        config = _make_reddit_config()

        override_dir = tmp_path / "custom_output"

        with patch("deep_thought.reddit.processor.process_rule") as mock_process:
            mock_process.return_value = CollectionResult()
            run_collection(
                reddit_client=mock_client,
                config=config,
                db_conn=in_memory_db,
                dry_run=False,
                force=False,
                rule_name_filter=None,
                output_override=override_dir,
            )
            call_kwargs = mock_process.call_args.kwargs
            assert call_kwargs["output_dir"] == override_dir


# ---------------------------------------------------------------------------
# run_collection — aggregate result
# ---------------------------------------------------------------------------


class TestRunCollectionAggregateResult:
    @pytest.mark.slow
    def test_aggregate_counts_across_multiple_rules(self, in_memory_db: sqlite3.Connection) -> None:
        """CollectionResult should aggregate counts from all processed rules."""
        mock_client = MagicMock()
        rule_a = _make_rule_config(name="rule_a")
        rule_b = _make_rule_config(name="rule_b")
        config = _make_reddit_config(rules=[rule_a, rule_b])

        fake_result_a = CollectionResult(posts_collected=3, posts_skipped=1)
        fake_result_b = CollectionResult(posts_collected=2, posts_updated=1)

        with patch("deep_thought.reddit.processor.process_rule", side_effect=[fake_result_a, fake_result_b]):
            aggregate = run_collection(
                reddit_client=mock_client,
                config=config,
                db_conn=in_memory_db,
                dry_run=False,
                force=False,
                rule_name_filter=None,
                output_override=None,
            )

        assert aggregate.posts_collected == 5
        assert aggregate.posts_skipped == 1
        assert aggregate.posts_updated == 1
