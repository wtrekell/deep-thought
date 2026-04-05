# Audio Tool — Issues

Outstanding issues from the 2026-03-23 code review. Critical and high severity issues were resolved in the same review cycle.

## Open — Low

### L-07: `format_duration` drops seconds for durations >= 1 hour

- **File:** `llms.py` (line ~99)
- A 1h 30s recording displays as "1h 0m". Acceptable for display purposes — the tool prioritises brevity over precision in the LLM context header.
- **Status:** Intentionally not fixed. Standard media-display convention.

### L-08: `format_timestamp` truncates rather than rounds

- **File:** `output.py` (line ~52)
- `int(seconds)` truncates. A segment at 59.9s shows `[00:59]`. Standard convention for media timestamps.
- **Status:** Intentionally not fixed. Standard media-timestamp convention.

---

## Resolved (2026-04-02)

### Cross-segment bigram/trigram hallucination check missing — FIXED

**File:** `hallucination.py`

The repetition detection in `detect_repetition()` only checked for repeated n-grams within a single segment. Hallucinations that span segment boundaries (e.g., a phrase split across the end of segment N and the start of segment N+1) were not detected. The window-level check compared whole segment texts but not their constituent n-grams.

Fixed (2026-04-02): Added Check 3 in `detect_repetition()`: all segment texts in the window are concatenated into a single word list and scanned for cross-boundary bigram/trigram repetition. Threshold scaled by `max(1, len(window_segments) // 2)` to reduce false positives in larger windows. Note: effectiveness of Check 3 relative to Check 2 is reduced when `window_size < 4` (default is 10; unaffected). Tests added in `tests/audio/test_hallucination.py`.

---

## Resolved (2026-03-30)

All medium, low (except L-07 and L-08), and test coverage issues resolved.

| ID | Severity | File | Issue | Resolution |
| --- | --- | --- | --- | --- |
| M-01 | Medium | `processor.py` | Diarization pipeline reloaded per file in batch | Moved pipeline loading to `process_batch`; passed as parameter to `process_file` |
| M-02 | Medium | `config.py` | `use_vad` config field exists but is never used | Removed `use_vad` from `HallucinationConfig`; added deprecation warning via `logger.warning` if field present in YAML |
| M-03 | Medium | `processor.py` | Snapshot filename collision in batch | Added source file stem and microseconds (`%f`) to timestamp format |
| M-04 | Medium | `hallucination.py` | Blocklist substring matching false positives | Short phrases (≤3 words) now require approximate exact match; longer phrases still use substring matching |
| M-05 | Medium | `cli.py` | `--engine` help text didn't document "auto" | Updated `--engine` help string to explain all three choices including "auto" |
| M-06 | Medium | `config.py` | Config parsers did no type validation | Added `isinstance` checks in all parser functions; `ValueError` raised on wrong types |
| M-07 | Medium | `cli.py` | `--dry-run` still loaded DB and models | Dry-run now exits early after file discovery, before DB init or engine creation |
| M-08 | Medium | `filters.py` | `collect_input_files` returned unsupported single-file inputs | Applied `is_supported_extension` to single-file input paths; returns `[]` for unsupported extensions |
| M-09 | Medium | `db/schema.py` | Migration SQL splitting was fragile | Replaced manual split loop with `conn.executescript()` |
| M-10 | Medium | `output.py` | `write_transcript` silently defaulted to paragraph mode for unknown `output_mode` | Raises `ValueError` for unrecognised mode strings |
| M-11 | Medium | `output.py` | YAML frontmatter string values not quoted | All string values now wrapped in double quotes |
| M-12 | Medium | `db/schema.py` | `get_data_dir()` env var path missing `/audio` | Changed `return Path(env_override)` to `return Path(env_override) / "audio"` |
| M-13 | Medium | `llms.py` | LLM files named `.llms.txt` / `.llms-full.txt` (hidden on Unix) | Removed leading dot; files now named `llms.txt` and `llms-full.txt` |
| M-14 | Medium | `llms.py` | `_strip_frontmatter` doesn't handle `---` inside content | Added comment acknowledging the limitation and why it is acceptable |
| M-15 | Medium | `db/queries.py` | No `conn.commit()` in `delete_processed_file`; caller responsibility undocumented | Added module-level docstring stating callers manage transaction commits |
| M-16 | Medium | `hallucination.py` | Trigram detection described but not implemented | Implemented trigram matching alongside bigrams using `collections.Counter` |
| L-01 | Low | `config.py` | `_PROJECT_ROOT` relied on file nesting depth | Already fixed via pyproject.toml walk-up in `db/schema.py`; confirmed no issue in `config.py` |
| L-02 | Low | `cli.py` | `_VERSION` hardcoded | Replaced with `_get_version()` using `importlib.metadata.version` with `PackageNotFoundError` fallback |
| L-03 | Low | `cli.py` / `llms.py` | `_strip_frontmatter` imported as private across modules | Renamed to `strip_frontmatter` (public); removed `# noqa: PLC2701` at import site |
| L-04 | Low | `hallucination.py` | `KNOWN_HALLUCINATION_PHRASES` missing underscore prefix | Renamed to `_KNOWN_HALLUCINATION_PHRASES` |
| L-05 | Low | `hallucination.py` | Bigram repetition check O(n²) | Replaced `bigrams.count()` loop with `collections.Counter` for O(n) |
| L-06 | Low | `processor.py` | Error handler re-hashed file | `file_hash` initialised to `None` before try-block; error handler reuses it when set |
| T-01 | Test | `test_db_schema.py` | Idempotency test used separate in-memory DBs | Fixed to call `run_migrations` twice on the **same** connection |
| T-02 | Test | `test_models.py` | No tests for `SpeakerSegment` or `ChunkResult` | Added `TestSpeakerSegment` and `TestChunkResult` classes |
| T-03 | Test | `test_cli.py` | No tests for `main()` entry point | Added `TestMainEntryPoint` covering dispatch, error exits, and fallback path |
| T-04 | Test | `test_cli.py` | No tests for CLI helper functions | Added `TestSetupLogging`, `TestLoadConfigFromArgs`, `TestResolveOutputRoot`, `TestGetVersion` |
| T-05 | Test | `test_filters.py` | No DB-backed duplicate detection test | Added `test_duplicate_detection_rejects_previously_processed_file` and non-success variant |
| T-06 | Test | `test_cli.py` | No test for `--llm` flag | Added `TestLlmFlag` covering `--llm` override and config fallback |
| T-07 | Test | `test_db_schema.py` | No tests for `get_connection()` or `get_database_path()` | Added `TestGetConnection` and `TestGetDatabasePath` classes |
| T-08 | Test | `test_hallucination.py` | No test for `_normalize_text()` | Added `TestNormalizeText` with 8 coverage cases |
| T-09 | Test | `test_db_queries.py`, `test_db_schema.py` | Duplicate `in_memory_db` fixtures shadow conftest | Removed local fixtures; both files now use the shared conftest fixture |

---

## Resolved (2026-03-23)

| ID | Severity | File | Issue | Resolution |
| --- | --- | --- | --- | --- |
| R-01 | High | `db/queries.py` | `INSERT OR REPLACE` destroys `created_at` on re-process | Replaced with `INSERT ... ON CONFLICT(file_path) DO UPDATE SET` excluding `created_at` |
| R-02 | High | `cli.py` | DB writes never committed — `conn.close()` without `conn.commit()` silently discards all records | Added `conn.commit()` before `conn.close()` in `cmd_transcribe` |
| R-03 | High | `db/queries.py` | Missing validation for required keys in `upsert_processed_file` — obscure `sqlite3.InterfaceError` | Added upfront key validation with descriptive `ValueError` |
| R-04 | High | `cli.py` | Boolean CLI overrides (`--diarize`, `--remove-fillers`) can't disable config-enabled features | Changed to `BooleanOptionalAction` (`--diarize`/`--no-diarize`); all overrides now use `is not None` |
| R-05 | High | `cli.py` | `parse_known_args` silently swallows typos and unknown flags | Added warning log when unrecognized arguments are detected |
| R-06 | High | `config.py` | No bounds validation for `pause_threshold` and `chunk_duration_minutes` | Added `> 0` checks in `validate_config` |
| R-07 | High | `engines/mlx_whisper_engine.py` | Temp chunk directory never cleaned up — orphaned `audio_chunks_*` dirs accumulate | Added `chunk_dir.rmdir()` in `finally` block after file cleanup |
