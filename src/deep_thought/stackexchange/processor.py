"""Rule engine and orchestration for the Stack Exchange Tool.

Coordinates fetching questions, applying filters, generating output files,
and writing state to the database. Handles per-question errors gracefully —
one failing question never aborts the rest of the collection run.
"""

from __future__ import annotations

import logging
import sqlite3  # noqa: TC003
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from deep_thought.progress import track_items
from deep_thought.stackexchange.filters import apply_rule_filters
from deep_thought.stackexchange.models import CollectedQuestionLocal
from deep_thought.stackexchange.output import generate_markdown, write_question_file

if TYPE_CHECKING:
    from deep_thought.stackexchange.client import StackExchangeClient
    from deep_thought.stackexchange.config import RuleConfig, StackExchangeConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit retry constants
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 10.0
_DEFAULT_RATE_LIMIT_COOLDOWN = 60.0

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CollectionResult:
    """Summary of a collection run (one or more rules)."""

    questions_collected: int = 0
    questions_skipped: int = 0
    questions_updated: int = 0
    questions_errored: int = 0
    errors: list[str] = field(default_factory=list)
    rate_limited: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_retry_delay(retry_after_header: str | None, attempt: int) -> float:
    """Return the number of seconds to wait before retrying after a 429.

    Prefers the ``Retry-After`` header value when available, plus a 1-second
    buffer to account for clock skew. Falls back to exponential backoff
    (10s, 20s, 40s, …) when the header is absent or non-numeric.

    Args:
        retry_after_header: Value of the ``Retry-After`` response header, or None.
        attempt: Zero-based retry attempt number.

    Returns:
        Delay in seconds.
    """
    if retry_after_header:
        try:
            return float(retry_after_header) + 1.0
        except (ValueError, TypeError):
            pass
    return _BASE_BACKOFF_SECONDS * (2.0**attempt)


def _process_single_question(
    question: dict[str, Any],
    answers: list[dict[str, Any]],
    question_comments: list[dict[str, Any]],
    answer_comments: dict[int, list[dict[str, Any]]],
    rule_config: RuleConfig,
    db_conn: sqlite3.Connection,
    output_dir: Path,
    date_prefix: str,
    *,
    dry_run: bool,
    force: bool,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_db",
) -> str:
    """Generate markdown, write output, and upsert the database record for one question.

    Checks the database for an existing record. If one is found and the answer
    count has not increased, the question is skipped. If answer count has grown,
    the question is reprocessed and the record is updated.

    Args:
        question: A Stack Exchange API question dict.
        answers: Pre-fetched answer dicts for this question.
        question_comments: Pre-fetched comment dicts on the question itself.
        answer_comments: Dict mapping answer_id to list of comment dicts for that answer.
        rule_config: The RuleConfig governing this collection.
        db_conn: An open SQLite connection.
        output_dir: Root output directory for markdown files.
        date_prefix: Pre-computed YYMMDD date string — shared with write_question_file
            to guarantee both use the same date even across a midnight boundary.
        dry_run: If True, skip all writes.
        force: If True, reprocess even if the question already exists in the DB.
        embedding_model: Optional MLX embedding model. When provided together
            with ``embedding_qdrant_client``, the question is embedded after writing.
        embedding_qdrant_client: Optional Qdrant client. Must be provided
            together with ``embedding_model`` for embedding to occur.
        qdrant_collection: Qdrant collection name to write embeddings to.

    Returns:
        One of "collected", "updated", or "skipped" indicating the outcome.

    Raises:
        Exception: Propagated from httpx or file I/O; callers must handle.
    """
    from deep_thought.stackexchange.db.queries import (  # noqa: PLC0415
        get_collected_question,
        upsert_collected_question,
    )

    question_id = int(question["question_id"])
    site = rule_config.site
    state_key = f"{question_id}:{site}:{rule_config.name}"

    existing_row = get_collected_question(db_conn, state_key)

    if existing_row is not None and not force:
        stored_answer_count = int(existing_row["answer_count"])
        live_answer_count = int(question.get("answer_count", 0))
        if live_answer_count <= stored_answer_count:
            logger.debug("Question %s unchanged (answers: %d), skipping.", state_key, stored_answer_count)
            return "skipped"
        logger.debug(
            "Question %s has new answers (%d -> %d), updating.",
            state_key,
            stored_answer_count,
            live_answer_count,
        )

    markdown_content = generate_markdown(
        question=question,
        answers=answers,
        question_comments=question_comments,
        answer_comments=answer_comments,
        rule_name=rule_config.name,
        site=site,
    )

    is_update = existing_row is not None

    if not dry_run:
        written_path = write_question_file(
            content=markdown_content,
            output_dir=output_dir,
            rule_name=rule_config.name,
            question_id=question_id,
            title=str(question.get("title", "")),
            date_prefix=date_prefix,
        )
        output_path_str = str(written_path)

        local_question = CollectedQuestionLocal.from_api(
            api_question=question,
            rule_name=rule_config.name,
            site=site,
            output_path=output_path_str,
        )

        if embedding_model is not None and embedding_qdrant_client is not None:
            try:
                from deep_thought.embeddings import strip_frontmatter as _strip_frontmatter  # noqa: PLC0415
                from deep_thought.stackexchange.embeddings import (  # noqa: PLC0415
                    write_embedding as _write_se_embedding,
                )

                raw_md = Path(output_path_str).read_text(encoding="utf-8")
                embed_content = f"Title: {local_question.title}\n\n{_strip_frontmatter(raw_md)}"
                _write_se_embedding(
                    embed_content,
                    local_question,
                    embedding_model,
                    embedding_qdrant_client,
                    qdrant_collection,
                )
            except Exception as embed_err:
                logger.warning("Embedding failed for question %s: %s", state_key, embed_err)

        upsert_collected_question(db_conn, local_question.to_dict())

    return "updated" if is_update else "collected"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _process_rule(
    se_client: StackExchangeClient,
    rule_config: RuleConfig,
    db_conn: sqlite3.Connection,
    output_dir: Path,
    *,
    dry_run: bool,
    force: bool,
    global_question_count: int,
    max_questions_per_run: int,
    generate_llms_files: bool = True,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_db",
) -> CollectionResult:
    """Fetch questions for a single rule, apply filters, batch-fetch answers/comments, and process each.

    Stops early when the global question cap is reached. Per-question exceptions
    are caught, logged, and counted — remaining questions continue processing.
    HTTP 429 errors set ``result.rate_limited`` so the inter-rule cooldown fires
    in ``run_collection``.

    Args:
        se_client: The StackExchangeClient for API calls.
        rule_config: The RuleConfig governing this rule's collection.
        db_conn: An open SQLite connection for reading/writing state.
        output_dir: Root directory for markdown output files.
        dry_run: If True, log what would happen without writing anything.
        force: If True, ignore existing state and reprocess all questions.
        global_question_count: Number of questions already collected this run (across all rules).
        max_questions_per_run: Hard cap on total questions collected per invocation.
        generate_llms_files: If True, regenerate llms.txt and llms-full.txt after processing.
        embedding_model: Optional MLX embedding model, threaded through to each question.
        embedding_qdrant_client: Optional Qdrant client, threaded through to each question.
        qdrant_collection: Qdrant collection name to write embeddings to.

    Returns:
        A CollectionResult summarising this rule's outcome.
    """
    result = CollectionResult()

    if global_question_count >= max_questions_per_run:
        logger.info("Global question cap (%d) reached before rule '%s'.", max_questions_per_run, rule_config.name)
        return result

    logger.info("Processing rule '%s' (site: %s).", rule_config.name, rule_config.site)

    # Build tagged param: API expects semicolon-separated tags for AND matching
    tagged_param: str | None = ";".join(rule_config.tags.include) if rule_config.tags.include else None

    # Fetch questions with retry on rate limit
    questions: list[dict[str, Any]] | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            questions = se_client.get_questions(
                site=rule_config.site,
                tagged=tagged_param,
                sort=rule_config.sort,
                order=rule_config.order,
                max_questions=rule_config.max_questions,
            )
            break
        except httpx.HTTPStatusError as http_error:
            status_code = http_error.response.status_code
            if status_code == 429:
                retry_after = http_error.response.headers.get("Retry-After")
                delay = _get_retry_delay(retry_after, attempt)
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "Rate limited fetching questions for rule '%s' (attempt %d/%d). Waiting %.0fs.",
                        rule_config.name,
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    result.rate_limited = True
                    error_message = (
                        f"Rate limited fetching questions for rule '{rule_config.name}' "
                        f"after {_MAX_RETRIES} retries: {http_error}"
                    )
                    logger.error(error_message)
                    result.errors.append(error_message)
                    result.questions_errored += 1
                    return result
            else:
                error_message = f"HTTP error fetching questions for rule '{rule_config.name}': {http_error}"
                logger.error(error_message)
                result.errors.append(error_message)
                result.questions_errored += 1
                return result
        except Exception as fetch_error:
            error_message = f"Failed to fetch questions for rule '{rule_config.name}': {fetch_error}"
            logger.error(error_message)
            result.errors.append(error_message)
            result.questions_errored += 1
            return result

    if questions is None:
        return result

    # Apply client-side filters (including tags.any OR logic and keyword/age/score checks)
    passing_questions = [q for q in questions if apply_rule_filters(q, rule_config)]

    if not passing_questions:
        logger.info("Rule '%s': no questions passed filters.", rule_config.name)
        return result

    # Track questions that were filtered out
    result.questions_skipped += len(questions) - len(passing_questions)

    # Compute date prefix once for the whole rule so all files share the same date
    date_prefix = datetime.now(tz=UTC).strftime("%y%m%d")

    # Batch-fetch answers for all passing question IDs in one round-trip
    passing_question_ids = [int(q["question_id"]) for q in passing_questions]
    try:
        answers_by_question_id = se_client.get_answers(
            question_ids=passing_question_ids,
            site=rule_config.site,
            max_answers_per_question=rule_config.max_answers_per_question,
        )
    except Exception as answers_err:
        error_message = f"Failed to fetch answers for rule '{rule_config.name}': {answers_err}"
        logger.error(error_message)
        result.errors.append(error_message)
        # Continue with empty answers rather than aborting — question bodies are still useful
        answers_by_question_id = {qid: [] for qid in passing_question_ids}

    # Batch-fetch question comments and answer comments when configured
    question_comments_by_id: dict[int, list[dict[str, Any]]] = {qid: [] for qid in passing_question_ids}
    answer_comments_by_answer_id: dict[int, list[dict[str, Any]]] = {}

    if rule_config.include_comments:
        try:
            question_comments_by_id = se_client.get_question_comments(
                question_ids=passing_question_ids,
                site=rule_config.site,
                max_comments=rule_config.max_comments_per_question,
            )
        except Exception as qcomments_err:
            logger.warning("Failed to fetch question comments for rule '%s': %s", rule_config.name, qcomments_err)

        # Collect all answer IDs across all passing questions for batch comment fetch
        all_answer_ids: list[int] = []
        for qid in passing_question_ids:
            all_answer_ids.extend(int(a["answer_id"]) for a in answers_by_question_id.get(qid, []))

        if all_answer_ids:
            try:
                answer_comments_by_answer_id = se_client.get_answer_comments(
                    answer_ids=all_answer_ids,
                    site=rule_config.site,
                    max_comments=rule_config.max_comments_per_question,
                )
            except Exception as acomments_err:
                logger.warning("Failed to fetch answer comments for rule '%s': %s", rule_config.name, acomments_err)

    # Process each passing question individually with per-item error isolation
    for question in track_items(passing_questions, description=f"Rule: {rule_config.name}"):
        remaining_capacity = (
            max_questions_per_run - global_question_count - result.questions_collected - result.questions_updated
        )
        if remaining_capacity <= 0:
            logger.info("Global question cap reached during rule '%s'.", rule_config.name)
            break

        question_id = int(question["question_id"])
        state_key = f"{question_id}:{rule_config.site}:{rule_config.name}"

        try:
            question_answers = answers_by_question_id.get(question_id, [])
            question_level_comments = question_comments_by_id.get(question_id, [])
            answer_level_comments = {
                int(a["answer_id"]): answer_comments_by_answer_id.get(int(a["answer_id"]), []) for a in question_answers
            }

            action = _process_single_question(
                question=question,
                answers=question_answers,
                question_comments=question_level_comments,
                answer_comments=answer_level_comments,
                rule_config=rule_config,
                db_conn=db_conn,
                output_dir=output_dir,
                date_prefix=date_prefix,
                dry_run=dry_run,
                force=force,
                embedding_model=embedding_model,
                embedding_qdrant_client=embedding_qdrant_client,
                qdrant_collection=qdrant_collection,
            )

            if action == "skipped":
                result.questions_skipped += 1
            elif action == "updated":
                result.questions_updated += 1
                logger.debug("Updated question %s.", state_key)
            else:
                result.questions_collected += 1
                logger.debug("Collected question %s.", state_key)

        except httpx.HTTPStatusError as http_error:
            status_code = http_error.response.status_code
            if status_code == 429:
                retry_after = http_error.response.headers.get("Retry-After")
                delay = _get_retry_delay(retry_after, attempt=0)
                error_message = f"Rate limited processing question {state_key}. Waiting {delay:.0f}s."
                logger.warning(error_message)
                result.errors.append(error_message)
                result.questions_errored += 1
                result.rate_limited = True
                time.sleep(delay)
            else:
                error_message = f"HTTP error processing question {state_key}: {http_error}"
                logger.error(error_message)
                result.errors.append(error_message)
                result.questions_errored += 1
        except Exception as question_error:
            error_message = f"Error processing question {state_key}: {question_error}"
            logger.error(error_message)
            result.errors.append(error_message)
            result.questions_errored += 1

    # Generate llms index files after all questions in the rule are processed
    if not dry_run and generate_llms_files and result.questions_collected + result.questions_updated > 0:
        try:
            from deep_thought.stackexchange.llms import (  # noqa: PLC0415
                build_summaries_from_directory,
                write_llms_full,
                write_llms_index,
            )

            rule_output_dir = output_dir / rule_config.name
            summaries = build_summaries_from_directory(rule_output_dir)
            if summaries:
                write_llms_index(summaries, rule_output_dir)
                write_llms_full(summaries, rule_output_dir)
        except Exception as llms_err:
            logger.warning("LLMs file generation failed for rule '%s': %s", rule_config.name, llms_err)

    return result


def run_collection(
    se_client: StackExchangeClient,
    config: StackExchangeConfig,
    db_conn: sqlite3.Connection,
    *,
    dry_run: bool,
    force: bool,
    rule_name_filter: str | None,
    output_override: Path | None,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_db",
) -> CollectionResult:
    """Run the full collection cycle across all configured rules.

    Applies an optional rule name filter to run only a specific rule.
    Accumulates results across all rules into a single CollectionResult.
    When rate limiting is detected on a rule, pauses before the next rule
    to let the quota window reset.

    Args:
        se_client: The StackExchangeClient for API calls.
        config: The loaded StackExchangeConfig with all rules and global settings.
        db_conn: An open SQLite connection for reading/writing state.
        dry_run: If True, no writes are made to disk or the database.
        force: If True, ignore existing state and reprocess all questions.
        rule_name_filter: If set, only the rule with this name is processed.
        output_override: If set, use this directory instead of config.output_dir.
        embedding_model: Optional MLX embedding model. Passed through to each
            ``_process_rule`` call so questions are embedded as they are collected.
        embedding_qdrant_client: Optional Qdrant client. Passed through to
            each ``_process_rule`` call for writing embeddings.
        qdrant_collection: Qdrant collection name to write embeddings to.

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

    global_question_count = 0
    total_rules = len(rules_to_run)

    for rule_index, rule_config in enumerate(track_items(rules_to_run, description="Processing rules")):
        rule_result = _process_rule(
            se_client=se_client,
            rule_config=rule_config,
            db_conn=db_conn,
            output_dir=output_dir,
            dry_run=dry_run,
            force=force,
            global_question_count=global_question_count,
            max_questions_per_run=config.max_questions_per_run,
            generate_llms_files=config.generate_llms_files,
            embedding_model=embedding_model,
            embedding_qdrant_client=embedding_qdrant_client,
            qdrant_collection=qdrant_collection,
        )

        aggregate_result.questions_collected += rule_result.questions_collected
        aggregate_result.questions_skipped += rule_result.questions_skipped
        aggregate_result.questions_updated += rule_result.questions_updated
        aggregate_result.questions_errored += rule_result.questions_errored
        aggregate_result.errors.extend(rule_result.errors)
        if rule_result.rate_limited:
            aggregate_result.rate_limited = True

        global_question_count += rule_result.questions_collected + rule_result.questions_updated

        # Cooldown before the next rule when rate limiting was hit
        if rule_result.rate_limited and rule_index < total_rules - 1:
            logger.info(
                "Rate limiting detected; pausing %.0fs before next rule.",
                _DEFAULT_RATE_LIMIT_COOLDOWN,
            )
            time.sleep(_DEFAULT_RATE_LIMIT_COOLDOWN)

    # Persist API quota usage after the run
    if not dry_run and se_client.quota_remaining is not None:
        try:
            from deep_thought.stackexchange.db.queries import upsert_quota_usage  # noqa: PLC0415

            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            total_questions_processed = aggregate_result.questions_collected + aggregate_result.questions_updated
            upsert_quota_usage(db_conn, today, total_questions_processed, se_client.quota_remaining)
        except Exception as quota_err:
            logger.warning("Failed to persist quota usage: %s", quota_err)

    return aggregate_result
