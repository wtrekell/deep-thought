# GCal Tool — Known Issues

Issues identified during code review on 2026-03-23. Updated 2026-03-30 with additional findings and fixes. Severity ratings: high, medium, low.

---

## High Severity

### H1: DB record committed before output file written in create/update flows — FIXED

**Files:** `create.py:206`, `update.py:183`

`run_create` and `run_update` called `db_conn.commit()` immediately after `upsert_event()` and *before* calling `write_event_file()`. If the file write failed (e.g., disk full, permission error), the Calendar API event would already exist, the local DB record would be committed, but no markdown file would be on disk. The event would be orphaned — present in both Google Calendar and the local database but missing from the output directory.

Additionally, the CLI callers (`cmd_create`, `cmd_update`) also called `connection.commit()` after the function returned, creating a redundant double-commit.

**Fixed (2026-03-30):** Moved `upsert_event()` to after `write_event_file()` in both modules, and removed the internal `db_conn.commit()` calls. Transaction boundary ownership now rests exclusively with the CLI callers, consistent with how `run_pull` and other operations behave.

---

---

## Resolved (2026-04-02)

### A-01: Attendees stored as JSON string in frontmatter — FIXED

**Files:** `output.py`

Attendees were written to YAML frontmatter as a single JSON-encoded string value, requiring consumers to JSON-decode a value inside YAML. Display names containing `:` also produced invalid YAML.

Fixed (2026-04-02): Attendees now rendered as a proper YAML list. Each entry uses `- email: <addr>` with an optional `display_name: "<name>"` line. Both fields are quoted via `_escape_yaml_value()`. Tests updated.

---

### A-02: No validation of attendee emails before API call — FIXED

**Files:** `create.py`, `update.py`

Attendee entries from markdown frontmatter were passed directly to the Google Calendar API without format validation. Malformed entries (missing `@` or `.`) would fail at API call time with an opaque error.

Fixed (2026-04-02): Added `_validate_attendee_emails()` helper in `create.py`; imported and applied in `update.py`. Invalid entries are skipped with a `logger.warning`, allowing the event write to proceed with valid attendees.

---

### A-03: attendee display_name not YAML-escaped — FIXED

**Files:** `output.py`

Display names were written as unquoted YAML scalars. Names containing `:` (common in business calendar contacts, e.g. "Head: Marketing") produced structurally invalid YAML.

Fixed (2026-04-03): Both `email` and `display_name` fields in the attendee list are now passed through `_escape_yaml_value()`.

---

## Medium Severity — ALL RESOLVED (2026-03-30)

### M1: Missing transactions around multi-event upsert loops — FIXED

**Files:** `pull.py`

**Fixed (2026-03-30):** Wrapped the event processing loop in `_sync_single_calendar` with an explicit `SAVEPOINT`/`RELEASE`/`ROLLBACK TO` block. A savepoint is used instead of `BEGIN` because Python's `sqlite3` module may have already implicitly started a transaction (e.g. from `clear_sync_token`), and nested `BEGIN` would raise `OperationalError`. On any failure, the savepoint rolls back all writes for that calendar. Tests added.

---

### M2: sync_state table lacks updated_at / synced_at columns — FIXED

**File:** `db/migrations/002_add_sync_state_timestamps.sql` (new), `db/queries.py`

**Fixed (2026-03-30):** Created migration `002_add_sync_state_timestamps.sql` adding `updated_at` and `synced_at` columns to `sync_state` with epoch-placeholder defaults. Updated `upsert_sync_state` to populate both columns on every write. Schema version bumped to 2.

---

### M3: clear_sync_token / clear_all_sync_tokens don't update timestamps — FIXED

**File:** `db/queries.py`

**Fixed (2026-03-30):** Both functions now include `updated_at = :now` in their UPDATE statements. Addressed alongside M2.

---

### M4: Silent JSON deserialization failures in frontmatter output — FIXED

**File:** `output.py`

**Fixed (2026-03-30):** Added `logger.warning()` calls in both `except (json.JSONDecodeError, TypeError)` blocks for `attendees` and `recurrence`, including the event ID and error message. Tests added.

---

### M5: Pagination errors discard already-fetched results — FIXED

**File:** `client.py`

**Fixed (2026-03-30):** `list_events` now catches errors on page 2+ and returns the partial results already accumulated, logging a warning. Errors on the first page still propagate. Tests added.

---

### M6: Missing api_rate_limit_rpm validation — FIXED

**File:** `config.py`

**Fixed (2026-03-30):** Added `api_rate_limit_rpm > 0` validation in `validate_config()`. Tests added.

---

### M7: Overly broad exception catching in CLI \_run_command — FIXED

**File:** `cli.py`

**Fixed (2026-03-30):** Added explicit `HttpError` handler before the `except Exception` catch-all. The handler prints the HTTP status code and error details so the user sees the actual API error rather than a generic message.

---

### M8: Missing start < end validation in create/update flows — FIXED

**Files:** `create.py`, `update.py`

**Fixed (2026-03-30):** Added `_validate_start_before_end()` helper in `create.py` and imported it in `update.py`. Both `run_create` and `run_update` call it before making any API call, raising `ValueError` with a clear message if `start >= end`. Tests added.

---

### M9: Mixed named/positional SQL parameter styles — FIXED

**File:** `db/queries.py`

**Fixed (2026-03-30):** Standardized all query functions to use named parameters (`:param_name`) consistently across `get_calendar`, `delete_calendar`, `get_event`, `get_events_by_calendar`, `get_events_in_range`, `delete_event`, `delete_events_by_calendar`, `get_cancelled_events`, `get_sync_state`, `clear_sync_token`, `clear_all_sync_tokens`, `upsert_sync_state`, and `get_key_value`.

---

## Low Severity

### L1: Token file permissions no-op on Windows — DOCUMENTED (known limitation)

**File:** `client.py`

`token_path.chmod(0o600)` restricts the OAuth token file to owner-only access on Unix/macOS. On Windows this call has no effect — the file will retain default permissions, which may be world-readable.

**Status (2026-03-30):** A comment was added to `client.py` documenting this as a known platform limitation. Platform-specific permission enforcement (e.g. `icacls` on Windows) is out of scope for this tool.

---

### L2: No service-initialized check before API calls — FIXED

**File:** `client.py`

**Fixed (2026-03-30):** Added guard at the top of `_execute()`: raises `RuntimeError("Must call authenticate() before making API requests.")` if `self._service is None`. Tests added.

---

### L3: TOCTOU race in \_handle_save_config — FIXED

**File:** `cli.py`

**Fixed (2026-03-30):** Replaced check-then-write pattern with exclusive file creation (`open('xb')`). The open raises `FileExistsError` atomically if the file already exists, which is caught and surfaced as an error message.

---

### L4: No final-failure log in retry helper — FIXED

**File:** `client.py`

**Fixed (2026-03-30):** Added `logger.error()` after the retry loop when all attempts are exhausted. Tests added.

---

### L5: Snapshot helper calls datetime.now(UTC) twice — FIXED

**File:** `pull.py`

**Fixed (2026-03-30):** Captured `snapshot_time = datetime.now(UTC)` once and reused it for both the filename timestamp and the JSON payload `timestamp` field.

---

### L6: Large lookback/lookahead values not warned — FIXED

**File:** `config.py`

**Fixed (2026-03-30):** Added warnings in `validate_config()` for `lookback_days` or `lookahead_days` values greater than 365. The warning is also appended to the issues list so it surfaces in `gcal config` output. Tests added.

---

## Additional Changes (2026-03-30)

- **Migration parsing:** Replaced the manual `split(";")` approach in `run_migrations()` in `db/schema.py` with `conn.executescript()`, which is simpler and handles edge cases (e.g. semicolons in comments or strings) correctly.
- **strip_frontmatter:** Renamed `_strip_frontmatter` to `strip_frontmatter` (public) in `llms.py`. Updated callers and tests.
- **Dynamic version:** Replaced hardcoded `_VERSION = "0.1.0"` in `cli.py` with `_get_version()` using `importlib.metadata`, falling back to `"unknown"` if the package metadata is unavailable.
