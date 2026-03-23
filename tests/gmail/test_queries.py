"""Tests for the Gmail Tool SQL query functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from deep_thought.gmail.db.queries import (
    delete_all_emails,
    delete_emails_by_rule,
    delete_expired_cache,
    get_all_processed_emails,
    get_decision_cache,
    get_emails_by_rule,
    get_expired_cache_entries,
    get_key_value,
    get_processed_email,
    set_key_value,
    upsert_decision_cache,
    upsert_processed_email,
)

if TYPE_CHECKING:
    import sqlite3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_email_dict(
    message_id: str = "msg_001",
    rule_name: str = "newsletters",
    subject: str = "Test Subject",
    from_address: str = "sender@example.com",
    output_path: str = "data/gmail/export/newsletters/test.md",
    actions_taken: str = '["archive"]',
    status: str = "ok",
    created_at: str = "2026-03-23T00:00:00+00:00",
) -> dict[str, object]:
    """Build a processed email dict suitable for upsert_processed_email."""
    return {
        "message_id": message_id,
        "rule_name": rule_name,
        "subject": subject,
        "from_address": from_address,
        "output_path": output_path,
        "actions_taken": actions_taken,
        "status": status,
        "created_at": created_at,
    }


def _make_cache_dict(
    cache_key: str = "key_001",
    decision: str = '{"extracted": "content"}',
    ttl_seconds: int = 3600,
    created_at: str = "2026-03-23T00:00:00+00:00",
) -> dict[str, object]:
    """Build a decision cache dict suitable for upsert_decision_cache."""
    return {
        "cache_key": cache_key,
        "decision": decision,
        "ttl_seconds": ttl_seconds,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Processed emails
# ---------------------------------------------------------------------------


class TestUpsertProcessedEmail:
    """Tests for upsert_processed_email."""

    def test_insert_new_email(self, in_memory_db: sqlite3.Connection) -> None:
        """Should insert a new row when the message_id does not exist."""
        upsert_processed_email(in_memory_db, _make_email_dict())
        result = get_processed_email(in_memory_db, "msg_001")
        assert result is not None
        assert result["subject"] == "Test Subject"

    def test_update_existing_email(self, in_memory_db: sqlite3.Connection) -> None:
        """Should update mutable fields when the message_id already exists."""
        upsert_processed_email(in_memory_db, _make_email_dict())
        upsert_processed_email(in_memory_db, _make_email_dict(subject="Updated Subject"))
        result = get_processed_email(in_memory_db, "msg_001")
        assert result is not None
        assert result["subject"] == "Updated Subject"

    def test_preserves_created_at_on_update(self, in_memory_db: sqlite3.Connection) -> None:
        """The original created_at should not change on upsert."""
        original_created = "2026-03-20T00:00:00+00:00"
        upsert_processed_email(in_memory_db, _make_email_dict(created_at=original_created))
        upsert_processed_email(in_memory_db, _make_email_dict(created_at="2026-03-23T12:00:00+00:00"))
        result = get_processed_email(in_memory_db, "msg_001")
        assert result is not None
        assert result["created_at"] == original_created

    def test_sets_updated_at_and_synced_at(self, in_memory_db: sqlite3.Connection) -> None:
        """Both updated_at and synced_at should be set to a recent timestamp."""
        upsert_processed_email(in_memory_db, _make_email_dict())
        result = get_processed_email(in_memory_db, "msg_001")
        assert result is not None
        assert result["updated_at"] is not None
        assert result["synced_at"] is not None


class TestGetProcessedEmail:
    """Tests for get_processed_email."""

    def test_returns_none_for_missing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return None when no row matches the message_id."""
        result = get_processed_email(in_memory_db, "nonexistent")
        assert result is None

    def test_returns_dict_for_existing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return a dict with all columns when the row exists."""
        upsert_processed_email(in_memory_db, _make_email_dict())
        result = get_processed_email(in_memory_db, "msg_001")
        assert result is not None
        assert isinstance(result, dict)
        assert "message_id" in result


class TestGetEmailsByRule:
    """Tests for get_emails_by_rule."""

    def test_filters_by_rule_name(self, in_memory_db: sqlite3.Connection) -> None:
        """Should only return emails matching the specified rule."""
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_001", rule_name="newsletters"))
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_002", rule_name="receipts"))
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_003", rule_name="newsletters"))

        results = get_emails_by_rule(in_memory_db, "newsletters")
        assert len(results) == 2
        assert all(r["rule_name"] == "newsletters" for r in results)

    def test_returns_empty_for_unknown_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return an empty list when no emails match the rule."""
        result = get_emails_by_rule(in_memory_db, "nonexistent")
        assert result == []


class TestGetAllProcessedEmails:
    """Tests for get_all_processed_emails."""

    def test_returns_all_rows(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return every row in the table."""
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_001"))
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_002"))
        results = get_all_processed_emails(in_memory_db)
        assert len(results) == 2

    def test_returns_empty_on_empty_table(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return an empty list when no rows exist."""
        assert get_all_processed_emails(in_memory_db) == []


class TestDeleteEmails:
    """Tests for delete_all_emails and delete_emails_by_rule."""

    def test_delete_all(self, in_memory_db: sqlite3.Connection) -> None:
        """Should remove all rows and return the count."""
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_001"))
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_002"))
        deleted = delete_all_emails(in_memory_db)
        assert deleted == 2
        assert get_all_processed_emails(in_memory_db) == []

    def test_delete_by_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """Should only delete emails matching the specified rule."""
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_001", rule_name="newsletters"))
        upsert_processed_email(in_memory_db, _make_email_dict(message_id="msg_002", rule_name="receipts"))
        deleted = delete_emails_by_rule(in_memory_db, "newsletters")
        assert deleted == 1
        remaining = get_all_processed_emails(in_memory_db)
        assert len(remaining) == 1
        assert remaining[0]["rule_name"] == "receipts"


# ---------------------------------------------------------------------------
# Decision cache
# ---------------------------------------------------------------------------


class TestUpsertDecisionCache:
    """Tests for upsert_decision_cache."""

    def test_insert_new_entry(self, in_memory_db: sqlite3.Connection) -> None:
        """Should insert a new cache entry."""
        upsert_decision_cache(in_memory_db, _make_cache_dict())
        result = get_decision_cache(in_memory_db, "key_001")
        assert result is not None
        assert result["decision"] == '{"extracted": "content"}'

    def test_update_existing_entry(self, in_memory_db: sqlite3.Connection) -> None:
        """Should update decision and ttl on conflict."""
        upsert_decision_cache(in_memory_db, _make_cache_dict())
        upsert_decision_cache(in_memory_db, _make_cache_dict(decision='{"new": "value"}', ttl_seconds=7200))
        result = get_decision_cache(in_memory_db, "key_001")
        assert result is not None
        assert result["decision"] == '{"new": "value"}'
        assert result["ttl_seconds"] == 7200

    def test_preserves_created_at_on_update(self, in_memory_db: sqlite3.Connection) -> None:
        """The original created_at should not change on upsert."""
        original_created = "2026-03-20T00:00:00+00:00"
        upsert_decision_cache(in_memory_db, _make_cache_dict(created_at=original_created))
        upsert_decision_cache(in_memory_db, _make_cache_dict(created_at="2026-03-23T12:00:00+00:00"))
        result = get_decision_cache(in_memory_db, "key_001")
        assert result is not None
        assert result["created_at"] == original_created


class TestGetDecisionCache:
    """Tests for get_decision_cache."""

    def test_returns_none_for_missing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return None when no entry matches the cache_key."""
        assert get_decision_cache(in_memory_db, "nonexistent") is None


class TestExpiredCache:
    """Tests for cache expiry functions."""

    def test_get_expired_entries(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return entries where created_at + ttl_seconds is in the past."""
        # Entry created far in the past with short TTL — should be expired
        upsert_decision_cache(
            in_memory_db,
            _make_cache_dict(
                cache_key="expired_key",
                created_at="2020-01-01T00:00:00+00:00",
                ttl_seconds=1,
            ),
        )
        # Entry created recently with long TTL — should NOT be expired
        upsert_decision_cache(
            in_memory_db,
            _make_cache_dict(
                cache_key="fresh_key",
                created_at="2099-01-01T00:00:00+00:00",
                ttl_seconds=999999,
            ),
        )
        expired = get_expired_cache_entries(in_memory_db)
        expired_keys = [e["cache_key"] for e in expired]
        assert "expired_key" in expired_keys
        assert "fresh_key" not in expired_keys

    def test_delete_expired(self, in_memory_db: sqlite3.Connection) -> None:
        """Should delete only expired entries and return the count."""
        upsert_decision_cache(
            in_memory_db,
            _make_cache_dict(
                cache_key="expired_key",
                created_at="2020-01-01T00:00:00+00:00",
                ttl_seconds=1,
            ),
        )
        upsert_decision_cache(
            in_memory_db,
            _make_cache_dict(
                cache_key="fresh_key",
                created_at="2099-01-01T00:00:00+00:00",
                ttl_seconds=999999,
            ),
        )
        deleted = delete_expired_cache(in_memory_db)
        assert deleted == 1
        assert get_decision_cache(in_memory_db, "fresh_key") is not None
        assert get_decision_cache(in_memory_db, "expired_key") is None


# ---------------------------------------------------------------------------
# Key/value store
# ---------------------------------------------------------------------------


class TestKeyValue:
    """Tests for key_value get and set functions."""

    def test_get_returns_none_for_missing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should return None when the key does not exist."""
        assert get_key_value(in_memory_db, "nonexistent") is None

    def test_set_and_get_roundtrip(self, in_memory_db: sqlite3.Connection) -> None:
        """Should store a value and retrieve it by key."""
        set_key_value(in_memory_db, "test_key", "test_value")
        assert get_key_value(in_memory_db, "test_key") == "test_value"

    def test_overwrite_existing(self, in_memory_db: sqlite3.Connection) -> None:
        """Should overwrite the value when the key already exists."""
        set_key_value(in_memory_db, "test_key", "original")
        set_key_value(in_memory_db, "test_key", "updated")
        assert get_key_value(in_memory_db, "test_key") == "updated"
