"""Tests for the Gmail Tool processor and rule engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path
    from unittest.mock import MagicMock

from deep_thought.gmail.config import GmailConfig, RuleConfig
from deep_thought.gmail.processor import (
    _apply_actions,
    _forward_message,
    _process_single_email,
    _write_snapshot,
    process_rule,
    run_collection,
    run_send,
)

from .conftest import make_mock_message

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def basic_rule() -> RuleConfig:
    """Return a minimal rule config for testing."""
    return RuleConfig(
        name="test_rule",
        query="from:test@example.com",
        ai_instructions=None,
        actions=["archive"],
        append_mode=False,
    )


@pytest.fixture()
def basic_config(basic_rule: RuleConfig) -> GmailConfig:
    """Return a minimal GmailConfig with one rule."""
    return GmailConfig(
        credentials_path="src/config/gmail/credentials.json",
        token_path="data/gmail/token.json",
        scopes=["https://mail.google.com/"],
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.5-flash",
        gemini_rate_limit_rpm=15,
        gmail_rate_limit_rpm=250,
        retry_max_attempts=3,
        retry_base_delay_seconds=1,
        max_emails_per_run=100,
        clean_newsletters=False,
        decision_cache_ttl=3600,
        output_dir="data/gmail/export/",
        generate_llms_files=False,
        flat_output=False,
        rules=[basic_rule],
    )


# ---------------------------------------------------------------------------
# _write_snapshot
# ---------------------------------------------------------------------------


class TestWriteSnapshot:
    """Tests for _write_snapshot."""

    def test_creates_snapshot_file(self, tmp_path: Path) -> None:
        """Should create a JSON snapshot file in the snapshots directory."""
        messages = [{"id": "msg1"}, {"id": "msg2"}]
        snapshot_path = _write_snapshot(messages, tmp_path)
        assert snapshot_path.exists()
        assert snapshot_path.suffix == ".json"
        assert snapshot_path.parent.name == "snapshots"

    def test_snapshot_contains_messages(self, tmp_path: Path) -> None:
        """Should write the message data as JSON."""
        import json

        messages = [{"id": "msg1", "snippet": "Hello"}]
        snapshot_path = _write_snapshot(messages, tmp_path)
        loaded = json.loads(snapshot_path.read_text())
        assert loaded == messages

    def test_creates_snapshots_directory(self, tmp_path: Path) -> None:
        """Should create the snapshots subdirectory if missing."""
        data_dir = tmp_path / "data" / "gmail"
        messages: list[dict[str, Any]] = []
        snapshot_path = _write_snapshot(messages, data_dir)
        assert snapshot_path.parent.exists()


# ---------------------------------------------------------------------------
# _apply_actions
# ---------------------------------------------------------------------------


class TestApplyActions:
    """Tests for _apply_actions."""

    def test_archive_action(self, mock_gmail_client: MagicMock) -> None:
        """Should call modify_message to remove INBOX label."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["archive"], dry_run=False)
        mock_gmail_client.modify_message.assert_called_once_with("msg1", remove_labels=["INBOX"])
        assert applied == ["archive"]

    def test_mark_read_action(self, mock_gmail_client: MagicMock) -> None:
        """Should call modify_message to remove UNREAD label."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["mark_read"], dry_run=False)
        mock_gmail_client.modify_message.assert_called_once_with("msg1", remove_labels=["UNREAD"])
        assert applied == ["mark_read"]

    def test_trash_action(self, mock_gmail_client: MagicMock) -> None:
        """Should call trash_message."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["trash"], dry_run=False)
        mock_gmail_client.trash_message.assert_called_once_with("msg1")
        assert applied == ["trash"]

    def test_delete_action(self, mock_gmail_client: MagicMock) -> None:
        """Should call delete_message."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["delete"], dry_run=False)
        mock_gmail_client.delete_message.assert_called_once_with("msg1")
        assert applied == ["delete"]

    def test_label_action(self, mock_gmail_client: MagicMock) -> None:
        """Should look up or create label and apply it."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["label:Processed"], dry_run=False)
        mock_gmail_client.get_or_create_label.assert_called_once_with("Processed")
        mock_gmail_client.modify_message.assert_called_once_with("msg1", add_labels=["Label_123"])
        assert applied == ["label:Processed"]

    def test_remove_label_action(self, mock_gmail_client: MagicMock) -> None:
        """Should look up label and remove it."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["remove_label:OldLabel"], dry_run=False)
        mock_gmail_client.get_or_create_label.assert_called_once_with("OldLabel")
        mock_gmail_client.modify_message.assert_called_once_with("msg1", remove_labels=["Label_123"])
        assert applied == ["remove_label:OldLabel"]

    def test_dry_run_skips_execution(self, mock_gmail_client: MagicMock) -> None:
        """Should not call any client methods in dry-run mode."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["archive", "trash"], dry_run=True)
        mock_gmail_client.modify_message.assert_not_called()
        mock_gmail_client.trash_message.assert_not_called()
        assert applied == ["archive", "trash"]

    def test_unknown_action_skipped(self, mock_gmail_client: MagicMock) -> None:
        """Should skip unknown actions without adding them to applied list."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["nonexistent_action"], dry_run=False)
        assert applied == []

    def test_multiple_actions(self, mock_gmail_client: MagicMock) -> None:
        """Should apply all recognised actions in order."""
        applied = _apply_actions(mock_gmail_client, "msg1", ["archive", "mark_read"], dry_run=False)
        assert applied == ["archive", "mark_read"]
        assert mock_gmail_client.modify_message.call_count == 2

    def test_action_failure_continues(self, mock_gmail_client: MagicMock) -> None:
        """Should continue to the next action if one fails."""
        mock_gmail_client.modify_message.side_effect = [RuntimeError("fail"), None]
        applied = _apply_actions(mock_gmail_client, "msg1", ["archive", "mark_read"], dry_run=False)
        # archive fails, mark_read succeeds
        assert applied == ["mark_read"]

    def test_forward_action(self, mock_gmail_client: MagicMock) -> None:
        """Should call _forward_message for forward: actions."""
        # Set up raw message for forwarding
        from email.mime.text import MIMEText

        mime_message = MIMEText("test body")
        mime_message["To"] = "original@example.com"
        mime_message["Subject"] = "Test"
        mock_gmail_client.get_raw_message.return_value = mime_message.as_bytes()

        applied = _apply_actions(mock_gmail_client, "msg1", ["forward:dest@example.com"], dry_run=False)
        assert applied == ["forward:dest@example.com"]
        mock_gmail_client.get_raw_message.assert_called_once_with("msg1")
        mock_gmail_client.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# _forward_message
# ---------------------------------------------------------------------------


class TestForwardMessage:
    """Tests for _forward_message."""

    def test_modifies_to_header(self, mock_gmail_client: MagicMock) -> None:
        """Should replace the To header with the forward address."""
        from email.mime.text import MIMEText

        original_message = MIMEText("Newsletter content")
        original_message["To"] = "me@example.com"
        original_message["Subject"] = "Weekly Digest"
        original_message["From"] = "sender@example.com"
        mock_gmail_client.get_raw_message.return_value = original_message.as_bytes()

        _forward_message(mock_gmail_client, "msg1", "reader@example.com")

        sent_bytes = mock_gmail_client.send_message.call_args[0][0]
        import email as email_module

        forwarded = email_module.message_from_bytes(sent_bytes)
        assert forwarded["To"] == "reader@example.com"
        assert forwarded["Subject"] == "Weekly Digest"

    def test_removes_dkim_signature(self, mock_gmail_client: MagicMock) -> None:
        """Should strip DKIM-Signature to avoid validation failure."""
        from email.mime.text import MIMEText

        original_message = MIMEText("Content")
        original_message["To"] = "me@example.com"
        original_message["DKIM-Signature"] = "v=1; a=rsa-sha256; ..."
        mock_gmail_client.get_raw_message.return_value = original_message.as_bytes()

        _forward_message(mock_gmail_client, "msg1", "dest@example.com")

        sent_bytes = mock_gmail_client.send_message.call_args[0][0]
        import email as email_module

        forwarded = email_module.message_from_bytes(sent_bytes)
        assert forwarded["DKIM-Signature"] is None

    def test_removes_cc_and_bcc(self, mock_gmail_client: MagicMock) -> None:
        """Should clear Cc and Bcc headers."""
        from email.mime.text import MIMEText

        original_message = MIMEText("Content")
        original_message["To"] = "me@example.com"
        original_message["Cc"] = "cc@example.com"
        original_message["Bcc"] = "bcc@example.com"
        mock_gmail_client.get_raw_message.return_value = original_message.as_bytes()

        _forward_message(mock_gmail_client, "msg1", "dest@example.com")

        sent_bytes = mock_gmail_client.send_message.call_args[0][0]
        import email as email_module

        forwarded = email_module.message_from_bytes(sent_bytes)
        assert forwarded["Cc"] is None
        assert forwarded["Bcc"] is None

    def test_handles_missing_cc_and_bcc(self, mock_gmail_client: MagicMock) -> None:
        """Should not crash when original message lacks Cc and Bcc headers."""
        from email.mime.text import MIMEText

        original_message = MIMEText("Content without CC/BCC")
        original_message["To"] = "me@example.com"
        mock_gmail_client.get_raw_message.return_value = original_message.as_bytes()

        # Should not raise
        _forward_message(mock_gmail_client, "msg1", "dest@example.com")
        mock_gmail_client.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# _process_single_email
# ---------------------------------------------------------------------------


class TestProcessSingleEmail:
    """Tests for _process_single_email."""

    def test_processes_email_successfully(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should return ok status and apply actions."""
        message = make_mock_message(message_id="proc_msg_1")
        mock_gmail_client.get_message.return_value = message

        status, actions = _process_single_email(
            gmail_client=mock_gmail_client,
            message_stub={"id": "proc_msg_1"},
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
        )

        assert status == "ok"
        assert "archive" in actions

    def test_writes_output_file(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should create a markdown file in the output directory."""
        message = make_mock_message(message_id="proc_msg_2", subject="Invoice Q1")
        mock_gmail_client.get_message.return_value = message

        _process_single_email(
            gmail_client=mock_gmail_client,
            message_stub={"id": "proc_msg_2"},
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
        )

        rule_dir = tmp_path / "test_rule"
        assert rule_dir.exists()
        markdown_files = list(rule_dir.glob("*.md"))
        assert len(markdown_files) == 1

    def test_dry_run_skips_write(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should not create output files in dry-run mode."""
        message = make_mock_message(message_id="proc_msg_3")
        mock_gmail_client.get_message.return_value = message

        status, _actions = _process_single_email(
            gmail_client=mock_gmail_client,
            message_stub={"id": "proc_msg_3"},
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=True,
            clean_newsletters=False,
            decision_cache_ttl=3600,
        )

        assert status == "ok"
        rule_dir = tmp_path / "test_rule"
        assert not rule_dir.exists() or len(list(rule_dir.glob("*.md"))) == 0

    def test_records_in_database(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should upsert processed email into the database."""
        from deep_thought.gmail.db.queries import get_processed_email

        message = make_mock_message(message_id="proc_msg_4")
        mock_gmail_client.get_message.return_value = message

        _process_single_email(
            gmail_client=mock_gmail_client,
            message_stub={"id": "proc_msg_4"},
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
        )

        record = get_processed_email(in_memory_db, "proc_msg_4")
        assert record is not None
        assert record["rule_name"] == "test_rule"

    def test_handles_processing_error(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should return error status when processing fails."""
        mock_gmail_client.get_message.side_effect = RuntimeError("API failure")

        status, actions = _process_single_email(
            gmail_client=mock_gmail_client,
            message_stub={"id": "fail_msg"},
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
        )

        assert status == "error"
        assert actions == []

    def test_handles_missing_message_id(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should return error when message stub has no id."""
        status, actions = _process_single_email(
            gmail_client=mock_gmail_client,
            message_stub={},
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
        )

        assert status == "error"
        assert actions == []

    def test_append_mode(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """Should use append_to_rule_file when append_mode is True."""
        append_rule = RuleConfig(
            name="newsletters",
            query="label:newsletter",
            ai_instructions=None,
            actions=[],
            append_mode=True,
        )
        message = make_mock_message(message_id="append_msg")
        mock_gmail_client.get_message.return_value = message

        status, _actions = _process_single_email(
            gmail_client=mock_gmail_client,
            message_stub={"id": "append_msg"},
            rule_config=append_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
        )

        assert status == "ok"
        aggregate_file = tmp_path / "newsletters" / "newsletters.md"
        assert aggregate_file.exists()


# ---------------------------------------------------------------------------
# process_rule
# ---------------------------------------------------------------------------


class TestProcessRule:
    """Tests for process_rule."""

    def test_processes_messages(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should process all messages returned by the query."""
        message_one = make_mock_message(message_id="rule_msg_1", subject="Email 1")
        message_two = make_mock_message(message_id="rule_msg_2", subject="Email 2")
        mock_gmail_client.list_messages.return_value = [{"id": "rule_msg_1"}, {"id": "rule_msg_2"}]
        mock_gmail_client.get_message.side_effect = [message_one, message_two]

        result = process_rule(
            gmail_client=mock_gmail_client,
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
            global_email_count=0,
            max_emails_per_run=100,
        )

        assert result.processed == 2
        assert result.errors == 0

    def test_skips_already_processed(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should skip emails that are already in the database."""
        from deep_thought.gmail.db.queries import upsert_processed_email

        # Pre-populate the database with one email
        upsert_processed_email(
            in_memory_db,
            {
                "message_id": "already_processed",
                "rule_name": "test_rule",
                "subject": "Old Email",
                "from_address": "sender@example.com",
                "output_path": "/path/to/file.md",
                "actions_taken": "[]",
                "status": "ok",
                "created_at": "2026-03-20T00:00:00+00:00",
                "updated_at": "2026-03-20T00:00:00+00:00",
                "synced_at": "2026-03-20T00:00:00+00:00",
            },
        )

        mock_gmail_client.list_messages.return_value = [{"id": "already_processed"}]

        result = process_rule(
            gmail_client=mock_gmail_client,
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
            global_email_count=0,
            max_emails_per_run=100,
        )

        assert result.skipped == 1
        assert result.processed == 0

    def test_force_mode_reprocesses(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should reprocess emails in force mode even if already in database."""
        from deep_thought.gmail.db.queries import upsert_processed_email

        upsert_processed_email(
            in_memory_db,
            {
                "message_id": "force_msg",
                "rule_name": "test_rule",
                "subject": "Old Email",
                "from_address": "sender@example.com",
                "output_path": "/path/to/file.md",
                "actions_taken": "[]",
                "status": "ok",
                "created_at": "2026-03-20T00:00:00+00:00",
                "updated_at": "2026-03-20T00:00:00+00:00",
                "synced_at": "2026-03-20T00:00:00+00:00",
            },
        )

        message = make_mock_message(message_id="force_msg")
        mock_gmail_client.list_messages.return_value = [{"id": "force_msg"}]
        mock_gmail_client.get_message.return_value = message

        result = process_rule(
            gmail_client=mock_gmail_client,
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            force=True,
            clean_newsletters=False,
            decision_cache_ttl=3600,
            global_email_count=0,
            max_emails_per_run=100,
        )

        assert result.processed == 1
        assert result.skipped == 0

    def test_respects_max_emails_cap(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should stop processing when max_emails_per_run is reached."""
        messages = [make_mock_message(message_id=f"cap_msg_{i}") for i in range(5)]
        mock_gmail_client.list_messages.return_value = [{"id": f"cap_msg_{i}"} for i in range(5)]
        mock_gmail_client.get_message.side_effect = messages

        result = process_rule(
            gmail_client=mock_gmail_client,
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
            global_email_count=0,
            max_emails_per_run=2,
        )

        assert result.processed <= 2

    def test_tracks_actions_taken(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_rule: RuleConfig,
        tmp_path: Path,
    ) -> None:
        """Should aggregate action counts in the result."""
        message = make_mock_message(message_id="action_msg")
        mock_gmail_client.list_messages.return_value = [{"id": "action_msg"}]
        mock_gmail_client.get_message.return_value = message

        result = process_rule(
            gmail_client=mock_gmail_client,
            rule_config=basic_rule,
            db_conn=in_memory_db,
            extractor=None,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            clean_newsletters=False,
            decision_cache_ttl=3600,
            global_email_count=0,
            max_emails_per_run=100,
        )

        assert "archive" in result.actions_taken
        assert result.actions_taken["archive"] == 1


# ---------------------------------------------------------------------------
# run_collection
# ---------------------------------------------------------------------------


class TestRunCollection:
    """Tests for run_collection."""

    def test_aggregates_multiple_rules(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """Should aggregate results across all rules."""
        rule_one = RuleConfig(
            name="rule_a",
            query="from:a@test.com",
            ai_instructions=None,
            actions=[],
            append_mode=False,
        )
        rule_two = RuleConfig(
            name="rule_b",
            query="from:b@test.com",
            ai_instructions=None,
            actions=[],
            append_mode=False,
        )

        config = GmailConfig(
            credentials_path="creds.json",
            token_path="token.json",
            scopes=["https://mail.google.com/"],
            gemini_api_key_env="GEMINI_API_KEY",
            gemini_model="gemini-2.5-flash",
            gemini_rate_limit_rpm=15,
            gmail_rate_limit_rpm=250,
            retry_max_attempts=3,
            retry_base_delay_seconds=1,
            max_emails_per_run=100,
            clean_newsletters=False,
            decision_cache_ttl=3600,
            output_dir=str(tmp_path),
            generate_llms_files=False,
            flat_output=False,
            rules=[rule_one, rule_two],
        )

        message_a = make_mock_message(message_id="coll_a")
        message_b = make_mock_message(message_id="coll_b")
        mock_gmail_client.list_messages.side_effect = [[{"id": "coll_a"}], [{"id": "coll_b"}]]
        mock_gmail_client.get_message.side_effect = [message_a, message_b]

        result = run_collection(
            gmail_client=mock_gmail_client,
            config=config,
            db_conn=in_memory_db,
        )

        assert result.processed == 2

    def test_rule_name_filter(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """Should only run the named rule when filter is specified."""
        rule_one = RuleConfig(
            name="target",
            query="from:a@test.com",
            ai_instructions=None,
            actions=[],
            append_mode=False,
        )
        rule_two = RuleConfig(
            name="skip_me",
            query="from:b@test.com",
            ai_instructions=None,
            actions=[],
            append_mode=False,
        )

        config = GmailConfig(
            credentials_path="creds.json",
            token_path="token.json",
            scopes=["https://mail.google.com/"],
            gemini_api_key_env="GEMINI_API_KEY",
            gemini_model="gemini-2.5-flash",
            gemini_rate_limit_rpm=15,
            gmail_rate_limit_rpm=250,
            retry_max_attempts=3,
            retry_base_delay_seconds=1,
            max_emails_per_run=100,
            clean_newsletters=False,
            decision_cache_ttl=3600,
            output_dir=str(tmp_path),
            generate_llms_files=False,
            flat_output=False,
            rules=[rule_one, rule_two],
        )

        message = make_mock_message(message_id="filter_msg")
        mock_gmail_client.list_messages.return_value = [{"id": "filter_msg"}]
        mock_gmail_client.get_message.return_value = message

        result = run_collection(
            gmail_client=mock_gmail_client,
            config=config,
            db_conn=in_memory_db,
            rule_name_filter="target",
        )

        assert result.processed == 1
        # list_messages should only be called once (for the target rule)
        assert mock_gmail_client.list_messages.call_count == 1

    def test_output_override(
        self,
        mock_gmail_client: MagicMock,
        in_memory_db: sqlite3.Connection,
        basic_config: GmailConfig,
        tmp_path: Path,
    ) -> None:
        """Should write files to the overridden output directory."""
        override_dir = tmp_path / "custom_output"
        message = make_mock_message(message_id="override_msg")
        mock_gmail_client.list_messages.return_value = [{"id": "override_msg"}]
        mock_gmail_client.get_message.return_value = message

        run_collection(
            gmail_client=mock_gmail_client,
            config=basic_config,
            db_conn=in_memory_db,
            output_override=override_dir,
        )

        assert override_dir.exists()
        assert any(override_dir.rglob("*.md"))


# ---------------------------------------------------------------------------
# run_send
# ---------------------------------------------------------------------------


class TestRunSend:
    """Tests for run_send."""

    def test_sends_email_from_markdown(self, mock_gmail_client: MagicMock, tmp_path: Path) -> None:
        """Should parse frontmatter and send the email."""
        message_file = tmp_path / "message.md"
        message_file.write_text(
            "---\nto: recipient@example.com\nsubject: Test Subject\n---\n\nHello, this is a test.",
            encoding="utf-8",
        )

        result = run_send(mock_gmail_client, message_file)

        assert result.message_id == "sent_123"
        assert result.thread_id == "thread_sent_123"
        mock_gmail_client.send_message.assert_called_once()

    def test_raises_on_missing_file(self, mock_gmail_client: MagicMock, tmp_path: Path) -> None:
        """Should raise FileNotFoundError for non-existent file."""
        missing_file = tmp_path / "nonexistent.md"
        with pytest.raises(FileNotFoundError):
            run_send(mock_gmail_client, missing_file)

    def test_raises_on_missing_frontmatter(self, mock_gmail_client: MagicMock, tmp_path: Path) -> None:
        """Should raise ValueError if file has no frontmatter."""
        message_file = tmp_path / "no_frontmatter.md"
        message_file.write_text("Just plain text with no frontmatter.", encoding="utf-8")

        with pytest.raises(ValueError, match="frontmatter"):
            run_send(mock_gmail_client, message_file)

    def test_raises_on_missing_to_field(self, mock_gmail_client: MagicMock, tmp_path: Path) -> None:
        """Should raise ValueError if 'to' field is missing."""
        message_file = tmp_path / "no_to.md"
        message_file.write_text("---\nsubject: Test\n---\n\nBody text.", encoding="utf-8")

        with pytest.raises(ValueError, match="to"):
            run_send(mock_gmail_client, message_file)

    def test_sends_with_cc_and_bcc(self, mock_gmail_client: MagicMock, tmp_path: Path) -> None:
        """Should include Cc and Bcc headers when specified."""
        message_file = tmp_path / "cc_message.md"
        message_file.write_text(
            "---\nto: main@example.com\nsubject: With CC\ncc: cc@example.com\nbcc: bcc@example.com\n---\n\nBody.",
            encoding="utf-8",
        )

        run_send(mock_gmail_client, message_file)

        sent_bytes = mock_gmail_client.send_message.call_args[0][0]
        import email as email_module

        sent_message = email_module.message_from_bytes(sent_bytes)
        assert sent_message["Cc"] == "cc@example.com"
        assert sent_message["Bcc"] == "bcc@example.com"

    def test_raises_on_unclosed_frontmatter(self, mock_gmail_client: MagicMock, tmp_path: Path) -> None:
        """Should raise ValueError for unclosed frontmatter."""
        message_file = tmp_path / "unclosed.md"
        message_file.write_text("---\nto: a@b.com\nsubject: test\nNo closing delimiter.", encoding="utf-8")

        with pytest.raises(ValueError, match="unclosed"):
            run_send(mock_gmail_client, message_file)
