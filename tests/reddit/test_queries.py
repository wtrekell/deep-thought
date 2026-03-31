"""Tests for db/queries.py — database query functions for the Reddit Tool.

All tests use an in-memory SQLite database seeded via the shared fixture so
no disk I/O occurs and each test starts with a clean state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deep_thought.reddit.db.queries import (
    delete_all_posts,
    delete_posts_by_rule,
    get_all_collected_posts,
    get_collected_post,
    get_key_value,
    get_posts_by_rule,
    get_posts_by_subreddit,
    set_key_value,
    upsert_collected_post,
)

if TYPE_CHECKING:
    import sqlite3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_post_dict(
    state_key: str = "abc123:python:rule1",
    post_id: str = "abc123",
    subreddit: str = "python",
    rule_name: str = "rule1",
    title: str = "Test Post",
    author: str = "test_user",
    score: int = 100,
    comment_count: int = 20,
    url: str = "https://reddit.com/r/python/comments/abc123/",
    is_video: int = 0,
    flair: str | None = None,
    word_count: int = 42,
    output_path: str = "/data/reddit/export/rule1/260101-abc123_test-post.md",
    status: str = "ok",
    created_at: str = "2026-01-01T10:00:00+00:00",
    updated_at: str = "2026-01-01T10:00:00+00:00",
    synced_at: str = "2026-01-01T10:00:00+00:00",
) -> dict[str, object]:
    """Build a minimal valid post dict for upsert tests."""
    return {
        "state_key": state_key,
        "post_id": post_id,
        "subreddit": subreddit,
        "rule_name": rule_name,
        "title": title,
        "author": author,
        "score": score,
        "comment_count": comment_count,
        "url": url,
        "is_video": is_video,
        "flair": flair,
        "word_count": word_count,
        "output_path": output_path,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "synced_at": synced_at,
    }


# ---------------------------------------------------------------------------
# upsert_collected_post
# ---------------------------------------------------------------------------


class TestUpsertCollectedPost:
    def test_inserts_new_post(self, in_memory_db: sqlite3.Connection) -> None:
        """Upserting a new post should create a row in the database."""
        post_data = _make_post_dict()
        upsert_collected_post(in_memory_db, post_data)
        in_memory_db.commit()

        result = get_collected_post(in_memory_db, "abc123:python:rule1")
        assert result is not None
        assert result["post_id"] == "abc123"
        assert result["title"] == "Test Post"

    def test_updates_existing_post_score(self, in_memory_db: sqlite3.Connection) -> None:
        """Re-upserting with a new score should update mutable fields."""
        original_post = _make_post_dict(score=100)
        upsert_collected_post(in_memory_db, original_post)
        in_memory_db.commit()

        updated_post = _make_post_dict(score=999)
        upsert_collected_post(in_memory_db, updated_post)
        in_memory_db.commit()

        result = get_collected_post(in_memory_db, "abc123:python:rule1")
        assert result is not None
        assert result["score"] == 999

    def test_preserves_created_at_on_update(self, in_memory_db: sqlite3.Connection) -> None:
        """Re-upserting must never overwrite the original created_at timestamp."""
        original_created_at = "2026-01-01T08:00:00+00:00"
        original_post = _make_post_dict(created_at=original_created_at)
        upsert_collected_post(in_memory_db, original_post)
        in_memory_db.commit()

        later_post = _make_post_dict(created_at="2026-06-01T12:00:00+00:00")
        upsert_collected_post(in_memory_db, later_post)
        in_memory_db.commit()

        result = get_collected_post(in_memory_db, "abc123:python:rule1")
        assert result is not None
        assert result["created_at"] == original_created_at

    def test_stores_null_flair(self, in_memory_db: sqlite3.Connection) -> None:
        """A post with no flair (None) should store NULL in the database."""
        post_data = _make_post_dict(flair=None)
        upsert_collected_post(in_memory_db, post_data)
        in_memory_db.commit()

        result = get_collected_post(in_memory_db, "abc123:python:rule1")
        assert result is not None
        assert result["flair"] is None

    def test_stores_flair_text(self, in_memory_db: sqlite3.Connection) -> None:
        """A post with flair text should persist that value correctly."""
        post_data = _make_post_dict(flair="Discussion")
        upsert_collected_post(in_memory_db, post_data)
        in_memory_db.commit()

        result = get_collected_post(in_memory_db, "abc123:python:rule1")
        assert result is not None
        assert result["flair"] == "Discussion"


# ---------------------------------------------------------------------------
# get_collected_post
# ---------------------------------------------------------------------------


class TestGetCollectedPost:
    def test_returns_none_for_missing_key(self, in_memory_db: sqlite3.Connection) -> None:
        """Querying for a state_key that does not exist should return None."""
        result = get_collected_post(in_memory_db, "nonexistent:sub:rule")
        assert result is None

    def test_returns_dict_for_existing_post(self, in_memory_db: sqlite3.Connection) -> None:
        """Querying a post that was inserted should return a non-None dict."""
        post_data = _make_post_dict()
        upsert_collected_post(in_memory_db, post_data)
        in_memory_db.commit()

        result = get_collected_post(in_memory_db, "abc123:python:rule1")
        assert isinstance(result, dict)
        assert result["state_key"] == "abc123:python:rule1"


# ---------------------------------------------------------------------------
# get_posts_by_rule
# ---------------------------------------------------------------------------


class TestGetPostsByRule:
    def test_returns_empty_list_for_unknown_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """Querying for a rule with no posts should return an empty list."""
        result = get_posts_by_rule(in_memory_db, "nonexistent_rule")
        assert result == []

    def test_returns_only_posts_for_given_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """Only posts belonging to the requested rule should be returned."""
        post_rule_a = _make_post_dict(
            state_key="aaa:python:rule_a",
            post_id="aaa",
            rule_name="rule_a",
        )
        post_rule_b = _make_post_dict(
            state_key="bbb:python:rule_b",
            post_id="bbb",
            rule_name="rule_b",
        )
        upsert_collected_post(in_memory_db, post_rule_a)
        upsert_collected_post(in_memory_db, post_rule_b)
        in_memory_db.commit()

        results = get_posts_by_rule(in_memory_db, "rule_a")
        assert len(results) == 1
        assert results[0]["rule_name"] == "rule_a"
        assert results[0]["post_id"] == "aaa"

    def test_returns_multiple_posts_for_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """Multiple posts under the same rule should all be returned."""
        for index in range(3):
            post_data = _make_post_dict(
                state_key=f"post{index}:python:my_rule",
                post_id=f"post{index}",
                rule_name="my_rule",
                created_at=f"2026-01-0{index + 1}T10:00:00+00:00",
            )
            upsert_collected_post(in_memory_db, post_data)
        in_memory_db.commit()

        results = get_posts_by_rule(in_memory_db, "my_rule")
        assert len(results) == 3


# ---------------------------------------------------------------------------
# get_posts_by_subreddit
# ---------------------------------------------------------------------------


class TestGetPostsBySubreddit:
    def test_returns_empty_list_for_unknown_subreddit(self, in_memory_db: sqlite3.Connection) -> None:
        """Querying for a subreddit with no posts should return an empty list."""
        result = get_posts_by_subreddit(in_memory_db, "unknownsub")
        assert result == []

    def test_returns_posts_filtered_by_subreddit(self, in_memory_db: sqlite3.Connection) -> None:
        """Only posts for the requested subreddit should be returned."""
        post_python = _make_post_dict(
            state_key="p1:python:rule1",
            post_id="p1",
            subreddit="python",
        )
        post_django = _make_post_dict(
            state_key="d1:django:rule1",
            post_id="d1",
            subreddit="django",
        )
        upsert_collected_post(in_memory_db, post_python)
        upsert_collected_post(in_memory_db, post_django)
        in_memory_db.commit()

        results = get_posts_by_subreddit(in_memory_db, "python")
        assert len(results) == 1
        assert results[0]["subreddit"] == "python"


# ---------------------------------------------------------------------------
# get_all_collected_posts
# ---------------------------------------------------------------------------


class TestGetAllCollectedPosts:
    def test_returns_empty_list_when_table_is_empty(self, in_memory_db: sqlite3.Connection) -> None:
        """An empty table should return an empty list."""
        results = get_all_collected_posts(in_memory_db)
        assert results == []

    def test_returns_all_posts(self, in_memory_db: sqlite3.Connection) -> None:
        """All inserted posts should be returned regardless of rule or subreddit."""
        for index in range(4):
            post_data = _make_post_dict(
                state_key=f"post{index}:sub{index}:rule{index}",
                post_id=f"post{index}",
                subreddit=f"sub{index}",
                rule_name=f"rule{index}",
                created_at=f"2026-01-0{index + 1}T10:00:00+00:00",
            )
            upsert_collected_post(in_memory_db, post_data)
        in_memory_db.commit()

        results = get_all_collected_posts(in_memory_db)
        assert len(results) == 4


# ---------------------------------------------------------------------------
# delete_all_posts
# ---------------------------------------------------------------------------


class TestDeleteAllPosts:
    def test_returns_zero_when_table_is_empty(self, in_memory_db: sqlite3.Connection) -> None:
        """Deleting from an empty table should return 0."""
        deleted_count = delete_all_posts(in_memory_db)
        in_memory_db.commit()
        assert deleted_count == 0

    def test_deletes_all_rows_and_returns_count(self, in_memory_db: sqlite3.Connection) -> None:
        """All rows should be removed and the correct count returned."""
        for index in range(3):
            post_data = _make_post_dict(
                state_key=f"p{index}:sub:rule",
                post_id=f"p{index}",
            )
            upsert_collected_post(in_memory_db, post_data)
        in_memory_db.commit()

        deleted_count = delete_all_posts(in_memory_db)
        in_memory_db.commit()

        assert deleted_count == 3
        assert get_all_collected_posts(in_memory_db) == []


# ---------------------------------------------------------------------------
# delete_posts_by_rule
# ---------------------------------------------------------------------------


class TestDeletePostsByRule:
    def test_deletes_only_matching_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """Only posts for the targeted rule should be removed; others remain."""
        post_keep = _make_post_dict(
            state_key="keep:sub:rule_keep",
            post_id="keep",
            rule_name="rule_keep",
        )
        post_delete = _make_post_dict(
            state_key="del:sub:rule_delete",
            post_id="del",
            rule_name="rule_delete",
        )
        upsert_collected_post(in_memory_db, post_keep)
        upsert_collected_post(in_memory_db, post_delete)
        in_memory_db.commit()

        deleted_count = delete_posts_by_rule(in_memory_db, "rule_delete")
        in_memory_db.commit()

        assert deleted_count == 1
        remaining = get_all_collected_posts(in_memory_db)
        assert len(remaining) == 1
        assert remaining[0]["rule_name"] == "rule_keep"

    def test_returns_zero_for_unknown_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """Targeting a rule with no posts should return 0."""
        deleted_count = delete_posts_by_rule(in_memory_db, "nonexistent_rule")
        assert deleted_count == 0


# ---------------------------------------------------------------------------
# set_key_value / get_key_value
# ---------------------------------------------------------------------------


class TestKeyValueStore:
    def test_set_and_get_key_value(self, in_memory_db: sqlite3.Connection) -> None:
        """Setting a key-value pair should make it retrievable."""
        set_key_value(in_memory_db, "my_key", "my_value")
        in_memory_db.commit()

        result = get_key_value(in_memory_db, "my_key")
        assert result == "my_value"

    def test_get_missing_key_returns_none(self, in_memory_db: sqlite3.Connection) -> None:
        """Getting a key that was never set should return None."""
        result = get_key_value(in_memory_db, "no_such_key")
        assert result is None

    def test_overwrites_existing_key(self, in_memory_db: sqlite3.Connection) -> None:
        """Setting the same key twice should overwrite the first value."""
        set_key_value(in_memory_db, "key", "first")
        in_memory_db.commit()

        set_key_value(in_memory_db, "key", "second")
        in_memory_db.commit()

        result = get_key_value(in_memory_db, "key")
        assert result == "second"
