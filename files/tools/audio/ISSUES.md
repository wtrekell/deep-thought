# Audio Tool — Issues

Outstanding issues from the 2026-03-23 code review. Critical and high severity issues were resolved in the same review cycle.

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

## Open — Medium

### M-01: Diarization pipeline reloaded for every file in batch

- **File:** `processor.py` (lines ~195-201)
- `load_diarization_pipeline` is called inside `process_file`, which runs once per file. Loading PyAnnote is expensive (model load, GPU init). A 50-file batch loads the pipeline 50 times.
- **Recommendation:** Load the pipeline once in `process_batch` and pass it into `process_file`.

### M-02: VAD configuration field exists but is never used

- **File:** `config.py` (line ~69), `hallucination.py`
- The config defines `use_vad: bool` and the YAML includes `use_vad: true`, but the hallucination module never references it. `detect_silence_gap` only checks Whisper's `no_speech_prob`. The field is dead code.
- **Recommendation:** Either implement VAD support, or remove `use_vad` from config and log a warning when set.

### M-03: Snapshot filename can collide in batch processing

- **File:** `processor.py` (lines ~68-69)
- Filenames use second-level precision. Two files processed in the same wall-clock second overwrite each other's snapshots.
- **Recommendation:** Include the source file stem or add microseconds to the timestamp.

### M-04: Blocklist substring matching produces false positives

- **File:** `hallucination.py` (lines ~31-55, 263-268)
- `check_blocklist` uses `if known_phrase in normalised_segment_text` (substring match). Legitimate speech containing "music", "applause", "bye bye" triggers false hits. The requirements specify these should be flagged "especially near silence or at end of audio" — that qualifier is not implemented.
- **Recommendation:** For short single-word entries, require approximate exact match (segment is 3 words or fewer), or add the silence/position qualifier.

### M-05: `--engine` CLI choices include "auto" but requirements say `[whisper|mlx]`

- **File:** `cli.py` (line ~371)
- Implementation adds "auto" as an explicit choice. Not necessarily wrong, but inconsistent with the documented flag signature.
- **Recommendation:** Update the requirements to include "auto".

### M-06: Config parsers do no type validation (except `_parse_limits_config`)

- **File:** `config.py` (lines ~105-228)
- `_parse_limits_config` validates integer types, but other parsers accept whatever YAML provides. `pause_threshold: "fast"` would store a string where a float is expected.
- **Recommendation:** Add type checks in each parser or in `validate_config`.

### M-07: `_build_config_with_overrides` dry-run still loads models

- **File:** `cli.py` (lines ~164-168)
- When `--dry-run` is set, the function prints a preview but continues to initialize the database, create the engine, and call `process_batch`. Engine creation may download models.
- **Recommendation:** Exit earlier in dry-run mode (before engine creation) with file discovery only.

### M-08: `collect_input_files` returns unsupported files for single-file input

- **File:** `filters.py` (lines ~170-171)
- When input is a single file, it's returned regardless of extension. `check_file` catches it later, but the "Found 1 audio file(s)" log is misleading.
- **Recommendation:** Apply `is_supported_extension` to single files, or update the docstring.

### M-09: Migration SQL splitting is fragile

- **File:** `db/schema.py` (lines ~186-195)
- Comment stripping and `;`-based splitting breaks on semicolons or `--` inside string literals.
- **Recommendation:** Use `conn.executescript()` or document the constraint for migration authors.

### M-10: `write_transcript` silently defaults to paragraph mode for unknown `output_mode`

- **File:** `output.py` (lines ~279-285)
- Unrecognized mode strings (typos) silently produce paragraph formatting.
- **Recommendation:** Raise `ValueError` for unrecognized modes.

### M-11: YAML frontmatter values are not quoted

- **File:** `output.py` (lines ~216-228)
- Filenames containing `:`, `#`, `{`, `[` produce invalid YAML frontmatter.
- **Recommendation:** Quote string values or use a YAML library.

### M-12: `get_data_dir()` env var path missing `/audio` subdirectory

- **File:** `db/schema.py` (lines ~42-45)
- When `DEEP_THOUGHT_DATA_DIR` is set, returns the path directly without appending `/audio`. Inconsistent with fallback path.
- **Recommendation:** Change to `Path(env_override) / "audio"`.

### M-13: LLM file naming mismatch with requirements

- **File:** `llms.py` (lines ~124, 161)
- Files named `.llms.txt` / `.llms-full.txt` (leading dot, hidden on Unix). Requirements show `{filename}.llms.txt` under a per-file `llm/` subdirectory.
- **Recommendation:** Align implementation with requirements or update requirements.

### M-14: `_strip_frontmatter` does not handle `---` inside content

- **File:** `llms.py` (lines ~50-77)
- Searches for closing `---` starting from line 1 and takes the first found. Content containing `---` on a line would truncate prematurely.
- **Recommendation:** Low risk given controlled frontmatter generation. Add a comment acknowledging the limitation.

### M-15: No `conn.commit()` in `delete_processed_file`

- **File:** `db/queries.py`
- DELETE executes but is never committed within the function. Caller responsibility is undocumented.
- **Recommendation:** Document caller commit responsibility or add commit.

### M-16: Trigram detection described but not implemented

- **File:** `hallucination.py` (line ~109)
- Docstring says "bigram/trigram matching" and requirements specify trigrams, but only bigrams are checked.
- **Recommendation:** Implement trigram matching or update docs.

## Open — Low

### L-01: `_PROJECT_ROOT` relies on file nesting depth

- **File:** `config.py` (line ~91)
- `Path(__file__).parent.parent.parent.parent` assumes fixed directory depth. Fragile to refactoring.
- **Recommendation:** Walk up looking for `pyproject.toml`.

### L-02: `_VERSION` hardcoded rather than read from package metadata

- **File:** `cli.py` (line ~34)
- Version `"0.1.0"` is hardcoded. Could drift from `pyproject.toml`.
- **Recommendation:** Use `importlib.metadata.version()` when the tool matures.

### L-03: `_strip_frontmatter` imported as private function across modules

- **File:** `cli.py` (line ~209)
- Cross-module import of `_strip_frontmatter` from `llms.py` with `# noqa: PLC2701`.
- **Recommendation:** Make it public (`strip_frontmatter`) since it's used across modules.

### L-04: `KNOWN_HALLUCINATION_PHRASES` missing underscore prefix

- **File:** `hallucination.py` (line ~31)
- Implementation standard says "prefix module-level constants with underscore." Other constants follow this.
- **Recommendation:** Rename to `_KNOWN_HALLUCINATION_PHRASES`.

### L-05: Bigram repetition check is O(n^2) per segment

- **File:** `hallucination.py` (lines ~141-143)
- `bigrams.count(bigram)` is O(n) for each bigram, making the loop O(n^2).
- **Recommendation:** Use `collections.Counter(bigrams)` for O(n) counting.

### L-06: Error handler re-hashes file that may have already been hashed

- **File:** `processor.py` (lines ~288-289)
- `compute_file_hash(source_path)` is called again in the error handler even though the hash was computed earlier. If the file is gone, this second call also fails.
- **Recommendation:** Reuse the `file_hash` variable from the earlier computation.

### L-07: `format_duration` drops seconds for durations >= 1 hour

- **File:** `llms.py` (line ~99)
- A 1h 30s recording displays as "1h 0m". Acceptable for display purposes.

### L-08: `format_timestamp` truncates rather than rounds

- **File:** `output.py` (line ~52)
- `int(seconds)` truncates. A segment at 59.9s shows `[00:59]`. Standard convention for media timestamps.

## Open — Test Coverage

### T-01: Idempotency test uses separate in-memory databases

- **File:** `test_db_schema.py` (lines ~94-99)
- `test_run_migrations_is_idempotent` opens two independent `:memory:` databases. Does not test actual idempotency.

### T-02: No tests for `SpeakerSegment` or `ChunkResult` dataclasses

- **File:** `test_models.py`
- Only `ProcessedFileLocal`, `TranscriptSegment`, `TranscriptionResult` are tested.

### T-03: No tests for `main()` entry point

- **File:** `test_cli.py`
- Argument parsing fallback, error handling branches, exit codes all untested.

### T-04: No tests for `_setup_logging`, `_load_config_from_args`, `_resolve_output_root`

- **File:** `test_cli.py`
- CLI helper functions with conditional logic are untested.

### T-05: No test for `check_file` duplicate detection via DB

- **File:** `test_filters.py`
- All `check_file` tests use `conn=None`. DB duplicate-detection path untested.

### T-06: No test for `--llm` flag / LLM aggregate file generation

- **File:** `test_cli.py`
- Tests use `generate_llms_files=False`. LLM file generation path entirely untested.

### T-07: No tests for `get_connection()` or `get_database_path()`

- **File:** `test_db_schema.py`
- Pragma setup and directory creation logic only exercised indirectly.

### T-08: No test for `_normalize_text()` helper

- **File:** `test_hallucination.py`
- Critical building block for repetition and blocklist detection has no direct tests.

### T-09: Duplicate `in_memory_db` fixtures shadow conftest

- **Files:** `test_db_queries.py`, `test_db_schema.py`
- Local fixtures shadow the shared `conftest.py` fixture unnecessarily.
