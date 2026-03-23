# GCal Tool — Known Issues

Issues identified during code review on 2026-03-23. Severity ratings: medium, low.

---

## Medium Severity

### M1: Missing transactions around multi-event upsert loops

**Files:** `pull.py` (event processing loop), `create.py`, `update.py`

Event upserts in the pull loop happen one at a time without explicit transaction boundaries. If an error occurs mid-loop, some events are persisted while others are lost. The `db_conn.commit()` at the end means partial state could accumulate on crash.

**Recommendation:** Wrap multi-event inserts in explicit `BEGIN`/`COMMIT` blocks with rollback on error.

---

### M2: sync_state table lacks updated_at / synced_at columns

**File:** `db/migrations/001_init_schema.sql` (sync_state table)

The `calendars` and `events` tables include `updated_at` and `synced_at` timestamp columns, but `sync_state` does not. This makes it impossible to track when a sync token was last modified locally.

**Recommendation:** Add `updated_at` and `synced_at` columns to `sync_state` in a future migration and update `upsert_sync_state`, `clear_sync_token`, and `clear_all_sync_tokens` to set these timestamps.

---

### M3: clear_sync_token / clear_all_sync_tokens don't update timestamps

**File:** `db/queries.py:335-354`

These functions set `sync_token = NULL` but don't update any timestamp column. Even without the M2 migration, if `updated_at` were added later these functions would need updating.

**Recommendation:** Address alongside M2 migration.

---

### M4: Silent JSON deserialization failures in frontmatter output

**File:** `output.py:96-115`

When `attendees` or `recurrence` JSON stored in the database is corrupt, the `except (json.JSONDecodeError, TypeError): pass` blocks silently skip the data. The user gets no indication that fields were omitted.

**Recommendation:** Add `logger.warning()` calls in the except blocks to surface deserialization failures.

---

### M5: Pagination errors discard already-fetched results

**File:** `client.py:257-288`

If `_execute()` raises during page 2+ of `list_events()`, all events accumulated from earlier pages are lost. The exception propagates with no partial results.

**Recommendation:** Consider returning partial results on error, or implementing pagination-level retry.

---

### M6: Missing api_rate_limit_rpm validation

**File:** `config.py:116-156`

`validate_config()` checks `retry_max_attempts > 0` but does not validate `api_rate_limit_rpm`. A negative value would produce a negative sleep interval (silently ignored by `time.sleep`), effectively disabling rate limiting. A value of 0 is handled by a guard clause in `_rate_limit()` but not surfaced to the user.

**Recommendation:** Add validation: `api_rate_limit_rpm` must be > 0.

---

### M7: Overly broad exception catching in CLI \_run_command

**File:** `cli.py:650-653`

The `except Exception` catch-all converts all errors (including specific `HttpError` responses like 403 Forbidden or 404 Not Found) into a generic "An unexpected error occurred" message. The actual API error details are hidden behind `--verbose`.

**Recommendation:** Add explicit handling for `HttpError` before the catch-all to surface the HTTP status code and error details.

---

### M8: Missing start < end validation in create/update flows

**Files:** `create.py`, `update.py`

Neither `run_create` nor `run_update` validates that `start_time < end_time` before sending the request to the Calendar API. Invalid date ranges fail at the API layer with an unhelpful error.

**Recommendation:** Add local validation before the API call, raising a `ValueError` with a clear message.

---

### M9: Mixed named/positional SQL parameter styles

**File:** `db/queries.py`

Upsert functions use named parameters (`:calendar_id`) while read/delete functions use positional parameters (`?`). Both are safe, but the inconsistency makes the code harder to maintain.

**Recommendation:** Standardize on one style across all query functions.

---

## Low Severity

### L1: Token file permissions are no-op on Windows

**File:** `client.py:160`

`token_path.chmod(0o600)` has no effect on Windows. The OAuth token file would have default (potentially world-readable) permissions.

**Recommendation:** Document as a known limitation, or use platform-specific permission enforcement.

---

### L2: No service-initialized check before API calls

**File:** `client.py:179`

If `authenticate()` has not been called before making API requests, `self._service` is `None` and the user gets a confusing `AttributeError`. The error does not indicate that `authenticate()` was never called.

**Recommendation:** Add an assertion in `_execute()`: `if self._service is None: raise RuntimeError("Must call authenticate() before making API requests")`.

---

### L3: TOCTOU race in \_handle_save_config

**File:** `cli.py:623-628`

The function checks `destination_path.exists()` then writes. Between the check and write, another process could create the file, causing silent overwrite.

**Recommendation:** Use exclusive file creation mode (`open('xb')`) instead of check-then-write.

---

### L4: No final-failure log message in retry helper

**File:** `client.py:64-73`

The retry helper logs warnings for each retry attempt but does not log when all retries are exhausted. The final failure re-raises silently.

**Recommendation:** Add `logger.error()` after the retry loop when all attempts fail.

---

### L5: Snapshot helper calls datetime.now(UTC) twice

**File:** `pull.py:70-75`

`_write_snapshot` calls `datetime.now(UTC)` once for the filename and again for the JSON payload. The two timestamps could differ by milliseconds.

**Recommendation:** Capture `now = datetime.now(UTC)` once and reuse it.

---

### L6: Large lookback/lookahead day values not warned

**File:** `config.py:143-147`

Values like `lookback_days: 10000` (27 years) are accepted without warning. The Calendar API will accept the request but it will be slow and return excessive data.

**Recommendation:** Add a validation warning for values > 365.
