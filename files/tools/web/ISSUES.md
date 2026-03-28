# Web Tool — Issues

Outstanding issues from code reviews. Critical and high severity issues were resolved in the 2026-03-23 review cycle.

## Resolved (2026-03-23)

| ID   | Severity | File                  | Issue                                                                                        | Resolution                                                                               |
| ---- | -------- | --------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| R-01 | Critical | `image_extractor.py`  | SSRF via `urlretrieve` with arbitrary URL schemes (`file://`, `ftp://`, cloud metadata)      | Added URL scheme validation (http/https only), replaced `urlretrieve` with `urlopen`     |
| R-02 | Critical | `output.py`           | Path traversal — `..` in URL path segments could write files outside output root             | Added resolved-path validation against output root                                       |
| R-03 | High     | `image_extractor.py`  | No file size limit on image downloads — could fill disk                                      | Added 50 MB size cap with size-limited read                                              |
| R-04 | High     | `config.py`, `cli.py` | Batch mode `input_url` always `None` — `CrawlConfig` had no `input_url` field                | Added `input_url` field to `CrawlConfig` and parsed it in `_parse_crawl_config`          |
| R-05 | High     | `cli.py`              | CLI `or`-based overrides silently ignored zero/false values (`--max-depth 0`, `--js-wait 0`) | Replaced all `or` fallbacks with explicit `is not None` checks                           |
| R-06 | High     | `cli.py`              | `--save-config` on crawl subparser declared but never handled                                | Added early guard in `cmd_crawl` to handle the flag                                      |
| R-07 | High     | `processor.py`        | Unhandled exceptions in mode runners crash the entire crawl                                  | Added broad `except Exception` handler after specific handlers in all three mode runners |
| R-08 | High     | `filters.py`          | Invalid regex patterns in config cause unhandled crash during crawl                          | Added `try/except re.error` around `re.compile` with warning log                         |
| R-09 | High     | `queries.py`          | `INSERT OR REPLACE` destroys `created_at` on re-crawl                                        | Replaced with `INSERT ... ON CONFLICT(url) DO UPDATE SET` excluding `created_at`         |
| R-10 | High     | `crawler.py`          | Stealth mode UA mismatch (HTTP header vs JS `navigator.userAgent`)                           | Moved user-agent and viewport to `browser.new_context()` so both values match            |
| R-11 | High     | `crawler.py`          | Stealth viewport randomization was a no-op                                                   | Resolved with R-10 — viewport set at context creation                                    |

## Resolved (2026-03-28)

| ID   | Severity | File                     | Issue                                                   | Resolution                        |
| ---- | -------- | ------------------------ | ------------------------------------------------------- | --------------------------------- |
| L-02 | Low      | `260322-requirements.md` | State Database section omitted `title` from column list | Added `title TEXT` to column list |

## Open — Medium

### M-01: Database connection never explicitly closed

- **File:** `cli.py`
- `initialize_database()` returns a connection that is never closed, even on error paths. The OS cleans up on exit, but dirty shutdowns can leave WAL/SHM files.
- **Recommendation:** Wrap database usage in a `finally` block or context manager.

### M-02: `_PROJECT_ROOT` relies on file nesting depth

- **File:** `config.py`
- `Path(__file__).parent.parent.parent.parent` assumes exact directory depth. Fragile to refactoring.
- **Recommendation:** Walk up looking for `pyproject.toml`, or use a shared utility.

### M-03: `parse_known_args` silently ignores typos and unknown flags

- **File:** `cli.py`
- Used for fallback-to-crawl pattern, but typos like `--steath` produce no error.
- **Recommendation:** Warn when `_remaining_args` is non-empty after subcommand resolution.

### M-04: `validate_config` not called in `cmd_crawl`

- **File:** `cli.py`
- Config validation runs in `cmd_config` but not before crawling. Invalid config values could reach the processor.
- **Recommendation:** Call `validate_config` after `_build_config_with_overrides` in `cmd_crawl`.

### M-05: `cmd_init` uses relative paths for output directories

- **File:** `cli.py`
- `Path("output/web/")` and `Path("docs/")` break when run from a different working directory.
- **Recommendation:** Use `_PROJECT_ROOT` or equivalent for absolute paths.

### M-06: No `output_dir` validation in `validate_config`

- **File:** `config.py`
- Numeric ranges and regex patterns are validated, but `output_dir` is not checked for empty string or invalid path characters.
- **Recommendation:** Add a non-empty string check.

### M-07: `_enqueue_children_from_db` is a no-op stub

- **File:** `processor.py`
- Incremental documentation-mode re-crawls (without `--force`) silently skip child pages of already-crawled pages. The BFS graph is truncated with no warning.
- **Recommendation:** At minimum log a warning. Better: store discovered child links in the database during initial crawl for replay.

### M-08: `conn` parameter in `_process_page` is unused

- **File:** `processor.py`
- `sqlite3.Connection` is accepted but never referenced inside the function. Misleading signature.
- **Recommendation:** Remove the parameter and update call sites.

### M-09: `_collect_article_urls` has no page count cap during collection

- **File:** `processor.py`
- `max_pages` is only applied after all article URLs are collected, not during. Wide graphs with high `index_depth` fetch unnecessary index pages.
- **Recommendation:** Pass `max_pages` into the collection function and stop early.

### M-10: Regex patterns recompiled on every call to `matches_any_pattern`

- **File:** `filters.py`
- Called once per URL per pattern. For large crawls with multiple patterns, compilation overhead adds up.
- **Recommendation:** Pre-compile patterns once at crawl start and pass compiled list through.

### M-11: `_TitleParser` only captures first text node inside `<title>`

- **File:** `converter.py`
- Titles with HTML entities (e.g., `&mdash;`) are split into multiple `handle_data` calls; only the first chunk is captured.
- **Recommendation:** Accumulate all text inside the `<title>` tag by appending to a list.

### M-12: YAML frontmatter title values are not quoted

- **File:** `output.py`
- Titles containing colons, quotes, brackets, or `#` produce invalid YAML frontmatter.
- **Recommendation:** Quote the title value or use a YAML serializer.

### M-13: Migration SQL parsing is fragile

- **File:** `db/schema.py`
- Comment stripping (`--` prefix) and statement splitting (`;`) are naive. Would break on semicolons or `--` inside string literals.
- **Recommendation:** Use `conn.executescript()` or document the constraint for migration authors.

### M-14: `get_data_dir()` env var path missing `/web` subdirectory

- **File:** `db/schema.py`
- When `DEEP_THOUGHT_DATA_DIR` is set, returns the path directly without appending `/web`. Inconsistent with the fallback path `data/web`.
- **Recommendation:** Change to `Path(env_override) / "web"`.

### M-15: No commit after write operations in queries

- **File:** `db/queries.py`
- `upsert_crawled_page` and `delete_crawled_page` never call `conn.commit()`. Caller responsibility is undocumented.
- **Recommendation:** Document caller commit responsibility, or add commits to write functions.

### M-16: Image filename extension derived from URL, not content type

- **File:** `image_extractor.py`
- URLs without extensions or with misleading extensions get wrong file types. Fallback to `.jpg` is arbitrary.
- **Recommendation:** Check `Content-Type` header and map to extension.

### M-17: `extract_image_urls` does not filter `data:` URIs

- **File:** `image_extractor.py`
- `data:` URIs are skipped in `download_images` (R-01 fix), but they still enter the extracted URL list unnecessarily.
- **Recommendation:** Filter `data:` URIs in `extract_image_urls` as well.

### M-18: Playwright started in `__init__`, not in `__enter__`

- **File:** `crawler.py`
- Asymmetry between where Playwright starts (init) and where it stops (exit). Leaks subprocess if not used as context manager.
- **Recommendation:** Move `sync_playwright().__enter__()` into `__enter__`.

### M-19: Cross-module import of private function `_strip_frontmatter`

- **File:** `processor.py`
- Imports a private function from `llms.py`. The `# noqa: PLC2701` suppression confirms the tooling flagged this.
- **Recommendation:** Make it public (`strip_frontmatter`) since it's used across modules.

## Open — Low

### L-01: `CrawledPageLocal.status_code` typed as `int`, but DB column is nullable

- **File:** `models.py`
- No sentinel for "no HTTP response" (DNS failure, connection refused).
- **Recommendation:** Consider `int | None` to match the database.

### L-03: Directory segments in output paths are not slugified

- **File:** `output.py`
- Only the filename is slugified. Directory names can contain spaces or special characters.
- **Recommendation:** Apply `slugify()` to directory segments.

### L-04: Query strings not stripped from extracted links

- **File:** `filters.py`
- Tracking parameters (e.g., `?utm_source=nav`) create duplicate page fetches.
- **Recommendation:** Consider stripping common tracking parameters or providing a config option.

### L-05: `count_words` has redundant list comprehension filter

- **File:** `converter.py`
- `[token for token in text.split() if token]` — the `if token` is redundant since `split()` already omits empties.
- **Recommendation:** Simplify to `len(text.split())`.

### L-06: Duplicated page-processing loop across three mode runners

- **File:** `processor.py`
- The fetch/process/upsert/error loop is nearly identical in `run_blog_mode`, `run_documentation_mode`, and `run_direct_mode`.
- **Recommendation:** Extract a shared `_process_url_list` helper.

### L-07: `write_llms_index` appends `.md` to display label

- **File:** `llms.py`
- Produces `[Introduction.md](...)` — matches spec literally but looks odd as a display label.
- **Recommendation:** Clarify whether `.md` in the label is intentional per requirements.

### L-08: `crawled_date` in `write_llms_full` labeled `crawled:` but represents generation time

- **File:** `llms.py`
- Misleading field name. Timestamp is set once before the loop, not per-page.
- **Recommendation:** Rename to `generated:` or use per-page crawl timestamps.

### L-09: Image extractor does not handle `srcset`, `<picture>`, or CSS backgrounds

- **File:** `image_extractor.py`
- Only `<img src>` is parsed. Modern pages use responsive image patterns.
- **Recommendation:** Consider `srcset` extraction as a follow-up enhancement.

## Open — Test Coverage

### T-01: No test file for `crawler.py`

Core page-fetching class (retry logic, stealth mode, context management) has zero test coverage.

### T-02: No test file for `llms.py`

LLM context file generation (`write_llms_full`, `write_llms_index`, `_strip_frontmatter`) untested.

### T-03: No test file for `image_extractor.py`

`extract_image_urls` and `download_images` untested.

### T-04: No test file for `config.py` core functions

`load_config`, `_parse_crawl_config`, `validate_config` (11 validation checks) untested directly.

### T-05: No test file for `models.py`

`CrawledPageLocal.to_dict()` untested.

### T-06: No tests for mode runner orchestration

`process()`, `run_blog_mode`, `run_documentation_mode`, `run_direct_mode` have no tests.

### T-07: `test_db.py` idempotency test uses separate in-memory databases

`test_running_init_twice_is_idempotent` opens two independent `:memory:` databases instead of calling init twice on the same database.

### T-08: `_process_page` success path only tested with `dry_run=True`

The `write_page`, image extraction, and `PageSummary` construction paths are never exercised.

### T-09: Unused fixtures `sample_html` and `blog_index_html` in `conftest.py`

Defined but never referenced by any test.
