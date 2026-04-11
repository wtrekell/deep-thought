"""Rule engine and orchestration for the Gmail Tool.

Coordinates fetching emails, applying filters, cleaning HTML, running AI
extraction, generating output files, applying post-collection actions, and
writing state to the database. Handles per-email errors gracefully — one
failing email never aborts the rest of the collection run.
"""

from __future__ import annotations

import email
import logging
import sqlite3  # noqa: TC003
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deep_thought.gmail.cleaner import clean_newsletter_html
from deep_thought.gmail.db.queries import (
    _now_utc_iso,
    delete_emails_by_rule,
    get_decision_cache,
    upsert_decision_cache,
    upsert_processed_email,
)
from deep_thought.gmail.filters import is_already_processed, is_within_max_emails
from deep_thought.gmail.models import CollectResult, ProcessedEmailLocal, SendResult, _extract_header
from deep_thought.gmail.output import (
    append_to_rule_file,
    extract_body_text,
    generate_email_markdown,
    write_email_file,
)
from deep_thought.progress import track_items
from deep_thought.text_utils import slugify as _shared_slugify

if TYPE_CHECKING:
    from deep_thought.gmail.client import GmailClient
    from deep_thought.gmail.config import GmailConfig, RuleConfig
    from deep_thought.gmail.extractor import GeminiExtractor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------


def _apply_actions(
    gmail_client: GmailClient,
    message_id: str,
    actions: list[str],
    *,
    dry_run: bool,
) -> list[str]:
    """Apply post-collection actions to a message.

    Returns the list of successfully applied actions. Failures are logged
    as warnings but do not abort processing.

    Args:
        gmail_client: An authenticated GmailClient.
        message_id: The Gmail message ID.
        actions: List of action strings from the rule config.
        dry_run: If True, log actions without executing them.

    Returns:
        List of action strings that were successfully applied.
    """
    applied: list[str] = []

    for action in actions:
        try:
            if dry_run:
                logger.info("[dry-run] Would apply action '%s' to %s", action, message_id)
                applied.append(action)
                continue

            if action == "archive":
                gmail_client.modify_message(message_id, remove_labels=["INBOX"])
            elif action == "mark_read":
                gmail_client.modify_message(message_id, remove_labels=["UNREAD"])
            elif action == "trash":
                gmail_client.trash_message(message_id)
            elif action == "delete":
                gmail_client.delete_message(message_id)
            elif action.startswith("label:"):
                label_name = action[6:]
                label_id = gmail_client.get_or_create_label(label_name)
                gmail_client.modify_message(message_id, add_labels=[label_id])
            elif action.startswith("remove_label:"):
                label_name = action[13:]
                existing_label_id = gmail_client.get_label(label_name)
                if existing_label_id is None:
                    logger.debug(
                        "remove_label: label '%s' does not exist in Gmail — skipping removal for %s",
                        label_name,
                        message_id,
                    )
                    continue
                gmail_client.modify_message(message_id, remove_labels=[existing_label_id])
            elif action.startswith("forward:"):
                forward_address = action[8:]
                _forward_message(gmail_client, message_id, forward_address)
            else:
                logger.warning("Unknown action '%s' — skipping.", action)
                continue

            applied.append(action)
            logger.debug("Action '%s' applied to %s", action, message_id)
        except Exception as action_error:
            logger.warning("Action '%s' failed for %s: %s", action, message_id, action_error)

    return applied


def _forward_message(
    gmail_client: GmailClient,
    message_id: str,
    forward_address: str,
) -> None:
    """Forward a message using the raw RFC 2822 technique.

    Fetches the full raw message, modifies only routing headers, and re-sends.
    Preserves the original MIME structure intact.

    Args:
        gmail_client: An authenticated GmailClient.
        message_id: The Gmail message ID to forward.
        forward_address: The email address to forward to.
    """
    raw_bytes = gmail_client.get_raw_message(message_id)
    message = email.message_from_bytes(raw_bytes)

    # Modify only routing headers — check existence before deleting
    if "To" in message:
        del message["To"]
    message["To"] = forward_address
    if "Cc" in message:
        del message["Cc"]
    if "Bcc" in message:
        del message["Bcc"]

    # Remove DKIM signature (would fail validation after header changes)
    if "DKIM-Signature" in message:
        del message["DKIM-Signature"]

    modified_bytes = message.as_bytes()
    gmail_client.send_message(modified_bytes)
    logger.info("Forwarded message %s to %s", message_id, forward_address)


# ---------------------------------------------------------------------------
# Per-email processing
# ---------------------------------------------------------------------------


def _process_single_email(
    gmail_client: GmailClient,
    message_stub: dict[str, Any],
    rule_config: RuleConfig,
    db_conn: sqlite3.Connection,
    extractor: GeminiExtractor | None,
    output_dir: Path,
    *,
    dry_run: bool,
    clean_newsletters: bool,
    decision_cache_ttl: int,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_db",
) -> tuple[str, list[str]]:
    """Fetch, process, and write output for a single email.

    Args:
        gmail_client: An authenticated GmailClient.
        message_stub: A message stub dict with 'id' key.
        rule_config: The rule config for this collection.
        db_conn: An open SQLite connection.
        extractor: A GeminiExtractor instance, or None to skip AI.
        output_dir: Root output directory.
        dry_run: If True, skip writing files and applying actions.
        clean_newsletters: If True, clean HTML before processing.
        decision_cache_ttl: Cache TTL in seconds for AI decisions.
        embedding_model: Optional MLX embedding model. When provided together
            with ``embedding_qdrant_client``, the email is embedded after writing.
        embedding_qdrant_client: Optional Qdrant client. Must be provided
            together with ``embedding_model`` for embedding to occur.
        qdrant_collection: Qdrant collection name for embeddings.

    Returns:
        A tuple of (status, actions_applied). Status is 'ok' or 'error'.
    """
    message_id = message_stub.get("id", "")
    if not message_id:
        logger.warning("Message stub missing 'id' field — skipping.")
        return "error", []

    try:
        message = gmail_client.get_message(message_id)
        plain_text, html_text = extract_body_text(message)

        # Use cleaned HTML if available and cleaning is enabled, else use plain text
        body_text = plain_text
        if html_text and (clean_newsletters or not plain_text):
            body_text = clean_newsletter_html(html_text)

        # AI extraction
        if extractor and rule_config.ai_instructions:
            cache_key = f"{message_id}:{rule_config.name}"
            cached = get_decision_cache(db_conn, cache_key)

            # Validate cache TTL before using
            cache_valid = False
            if cached is not None:
                try:
                    cache_created = datetime.fromisoformat(cached["created_at"])
                    cache_age = (datetime.now(tz=UTC) - cache_created).total_seconds()
                    cache_valid = cache_age < cached["ttl_seconds"]
                except (ValueError, KeyError):
                    cache_valid = False

            if cache_valid and cached is not None:
                body_text = cached["decision"]
                logger.debug("Using cached AI extraction for %s", message_id)
            else:
                extracted = extractor.extract(body_text, rule_config.ai_instructions)
                if extracted:
                    body_text = extracted
                    # Cache the result
                    now_iso = _now_utc_iso()
                    upsert_decision_cache(
                        db_conn,
                        {
                            "cache_key": cache_key,
                            "decision": extracted,
                            "ttl_seconds": decision_cache_ttl,
                            "created_at": now_iso,
                        },
                    )

        # Generate markdown (always — needed for embeddings even when not saving locally)
        actions_applied: list[str] = []
        subject = _extract_header(message, "Subject") or "(no subject)"
        markdown_content = generate_email_markdown(message, body_text, rule_config.name, rule_config.actions)

        # Write output based on save_mode
        date_str = datetime.now(tz=UTC).strftime("%y%m%d")

        if not dry_run:
            if rule_config.save_mode == "individual":
                output_path = write_email_file(markdown_content, output_dir, rule_config.name, subject, date_str)
                output_path_str = str(output_path)
            elif rule_config.save_mode == "append":
                output_path = append_to_rule_file(markdown_content, output_dir, rule_config.name)
                output_path_str = str(output_path)
            elif rule_config.save_mode == "both":
                output_path = write_email_file(markdown_content, output_dir, rule_config.name, subject, date_str)
                append_to_rule_file(markdown_content, output_dir, rule_config.name)
                output_path_str = str(output_path)
            else:
                output_path_str = ""

            # Embed into Qdrant
            if embedding_model is not None and embedding_qdrant_client is not None:
                try:
                    from deep_thought.embeddings import strip_frontmatter as _strip_frontmatter  # noqa: PLC0415
                    from deep_thought.gmail.embeddings import (  # noqa: PLC0415
                        write_embedding as _write_gmail_embedding,
                    )

                    embed_content = f"Subject: {subject}\n\n{_strip_frontmatter(markdown_content)}"
                    email_record_for_embed = ProcessedEmailLocal.from_message(
                        message=message,
                        rule_name=rule_config.name,
                        output_path=output_path_str,
                        actions=[],
                    )
                    _write_gmail_embedding(
                        embed_content,
                        email_record_for_embed,
                        embedding_model,
                        embedding_qdrant_client,
                        qdrant_collection,
                    )
                except Exception as embed_err:
                    logger.warning("Embedding failed for email %s: %s", message_id, embed_err)
        else:
            output_path_str = f"[dry-run] {output_dir / rule_config.name / _shared_slugify(subject)}.md"

        # Apply actions
        actions_applied = _apply_actions(gmail_client, message_id, rule_config.actions, dry_run=dry_run)

        # Record in database
        email_record = ProcessedEmailLocal.from_message(
            message=message,
            rule_name=rule_config.name,
            output_path=output_path_str,
            actions=actions_applied,
        )
        if not dry_run:
            upsert_processed_email(db_conn, email_record.to_dict())

        return "ok", actions_applied

    except Exception as processing_error:
        logger.warning("Failed to process email %s: %s", message_id, processing_error)
        return "error", []


# ---------------------------------------------------------------------------
# Rule processing
# ---------------------------------------------------------------------------


def process_rule(
    gmail_client: GmailClient,
    rule_config: RuleConfig,
    db_conn: sqlite3.Connection,
    extractor: GeminiExtractor | None,
    output_dir: Path,
    *,
    dry_run: bool,
    force: bool,
    clean_newsletters: bool,
    decision_cache_ttl: int,
    global_email_count: int,
    max_emails_per_run: int,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_db",
) -> CollectResult:
    """Process a single rule: query Gmail, fetch messages, process each.

    Args:
        gmail_client: An authenticated GmailClient.
        rule_config: The rule configuration.
        db_conn: An open SQLite connection.
        extractor: A GeminiExtractor instance, or None.
        output_dir: Root output directory.
        dry_run: Preview without writing.
        force: Clear state and reprocess.
        clean_newsletters: Strip HTML non-content.
        decision_cache_ttl: Cache TTL for AI decisions.
        global_email_count: Number of emails already processed this run.
        max_emails_per_run: Maximum emails per run.
        embedding_model: Optional MLX embedding model. Threaded through to
            ``_process_single_email`` to embed each collected email.
        embedding_qdrant_client: Optional Qdrant client. Threaded through to
            ``_process_single_email`` for writing embeddings.
        qdrant_collection: Qdrant collection name for embeddings.

    Returns:
        A CollectResult summarising this rule's processing.
    """
    result = CollectResult()

    logger.info("Processing rule '%s': %s", rule_config.name, rule_config.query)

    # Force mode: clear prior state for this rule
    if force and not dry_run:
        deleted = delete_emails_by_rule(db_conn, rule_config.name)
        logger.info("Force mode: cleared %d prior emails for rule '%s'", deleted, rule_config.name)

    # Query Gmail
    remaining = max_emails_per_run - global_email_count
    message_stubs = gmail_client.list_messages(rule_config.query, max_results=remaining)
    logger.info("Rule '%s': found %d messages", rule_config.name, len(message_stubs))

    for message_stub in track_items(message_stubs, description=f"Rule: {rule_config.name}"):
        if not is_within_max_emails(global_email_count + result.processed, max_emails_per_run):
            break

        message_id = message_stub.get("id", "")

        # Skip already processed (unless force mode)
        if not force and is_already_processed(message_id, db_conn):
            result.skipped += 1
            continue

        status, actions = _process_single_email(
            gmail_client=gmail_client,
            message_stub=message_stub,
            rule_config=rule_config,
            db_conn=db_conn,
            extractor=extractor,
            output_dir=output_dir,
            dry_run=dry_run,
            clean_newsletters=clean_newsletters,
            decision_cache_ttl=decision_cache_ttl,
            embedding_model=embedding_model,
            embedding_qdrant_client=embedding_qdrant_client,
            qdrant_collection=qdrant_collection,
        )

        if status == "ok":
            result.processed += 1
            for action in actions:
                result.actions_taken[action] = result.actions_taken.get(action, 0) + 1
        else:
            result.errors += 1
            result.error_messages.append(f"Email {message_id}: processing failed")

    return result


# ---------------------------------------------------------------------------
# Top-level orchestrators
# ---------------------------------------------------------------------------


def run_collection(
    gmail_client: GmailClient,
    config: GmailConfig,
    db_conn: sqlite3.Connection,
    extractor: GeminiExtractor | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
    rule_name_filter: str | None = None,
    output_override: Path | None = None,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_db",
) -> CollectResult:
    """Run all collection rules and aggregate results.

    Args:
        gmail_client: An authenticated GmailClient.
        config: The loaded GmailConfig.
        db_conn: An open SQLite connection.
        extractor: A GeminiExtractor instance, or None.
        dry_run: Preview without writing.
        force: Clear state and reprocess.
        rule_name_filter: Run only this rule (None = all rules).
        output_override: Override the output directory.
        embedding_model: Optional MLX embedding model. Passed through to each
            ``process_rule`` call so emails are embedded as they are collected.
        embedding_qdrant_client: Optional Qdrant client. Passed through to
            each ``process_rule`` call for writing embeddings.
        qdrant_collection: Qdrant collection name for embeddings.

    Returns:
        An aggregated CollectResult across all rules.
    """
    total_result = CollectResult()
    output_dir = Path(output_override) if output_override else Path(config.output_dir)

    global_email_count = 0

    for rule in track_items(config.rules, description="Processing rules"):
        if rule_name_filter and rule.name != rule_name_filter:
            continue

        rule_result = process_rule(
            gmail_client=gmail_client,
            rule_config=rule,
            db_conn=db_conn,
            extractor=extractor,
            output_dir=output_dir,
            dry_run=dry_run,
            force=force,
            clean_newsletters=config.clean_newsletters,
            decision_cache_ttl=config.decision_cache_ttl,
            global_email_count=global_email_count,
            max_emails_per_run=config.max_emails_per_run,
            embedding_model=embedding_model,
            embedding_qdrant_client=embedding_qdrant_client,
            qdrant_collection=qdrant_collection,
        )

        total_result.processed += rule_result.processed
        total_result.skipped += rule_result.skipped
        total_result.errors += rule_result.errors
        total_result.error_messages.extend(rule_result.error_messages)
        for action, count in rule_result.actions_taken.items():
            total_result.actions_taken[action] = total_result.actions_taken.get(action, 0) + count

        global_email_count += rule_result.processed

    return total_result


def run_send(
    gmail_client: GmailClient,
    message_path: Path,
) -> SendResult:
    """Send an email composed from a markdown file with YAML frontmatter.

    The markdown file must have frontmatter with 'to' and 'subject' fields.
    The body after frontmatter is sent as plain text.

    Args:
        gmail_client: An authenticated GmailClient.
        message_path: Path to the markdown file.

    Returns:
        A SendResult with the sent message's ID and thread ID.

    Raises:
        FileNotFoundError: If message_path does not exist.
        ValueError: If required frontmatter fields are missing.
    """
    import yaml

    if not message_path.exists():
        raise FileNotFoundError(f"Message file not found: {message_path}")

    raw_content = message_path.read_text(encoding="utf-8")

    # Parse frontmatter
    if not raw_content.startswith("---"):
        raise ValueError("Message file must start with YAML frontmatter (--- delimiter).")

    end_index = raw_content.find("---", 3)
    if end_index == -1:
        raise ValueError("Message file has unclosed YAML frontmatter.")

    frontmatter_text = raw_content[3:end_index].strip()
    body_text = raw_content[end_index + 3 :].strip()
    try:
        frontmatter: dict[str, Any] = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as yaml_error:
        raise ValueError(f"Invalid YAML frontmatter: {yaml_error}") from yaml_error

    to_address = frontmatter.get("to")
    subject = frontmatter.get("subject", "")
    cc_address = frontmatter.get("cc")
    bcc_address = frontmatter.get("bcc")

    if not to_address:
        raise ValueError("Message frontmatter must include a 'to' field.")

    # Build RFC 2822 message
    from email.mime.text import MIMEText

    mime_message = MIMEText(body_text, "plain", "utf-8")
    mime_message["To"] = to_address
    mime_message["Subject"] = subject
    if cc_address:
        mime_message["Cc"] = cc_address
    if bcc_address:
        mime_message["Bcc"] = bcc_address

    raw_bytes = mime_message.as_bytes()
    response = gmail_client.send_message(raw_bytes)

    return SendResult(
        message_id=response.get("id", ""),
        thread_id=response.get("threadId", ""),
    )
