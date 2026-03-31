# Research Tool — Known Issues

Issues identified during code review on 2026-03-23. Severity ratings: medium, low.

---

## Resolved (2026-03-30)

### M1: `to_frontmatter_dict()` was dead code

**File:** `models.py:169-199`

Removed `ResearchResult.to_frontmatter_dict()` and its tests. `_build_frontmatter()` in `output.py` is the sole source of truth for YAML frontmatter serialization.

---

### M2: No markdown escaping for source titles and snippets

**File:** `output.py:119-127`

Added `_escape_markdown()` helper that escapes `` ` ``, `*`, `_`, `[`, and `]`. Applied to source titles and snippets before rendering into `[title](url)` syntax. Tests added for the helper and for integration with `generate_research_markdown()`.

---

### M3: Config loading silently applied defaults for required fields

**File:** `config.py:95-101`

Changed `api_key_env`, `search_model`, `research_model`, and `output_dir` to use direct key access (`raw_dict["key"]`) in `load_config()`. Missing required fields now raise `KeyError` immediately. Updated affected tests to include all required fields in their config fixtures.

---

### M4: Config validation did not check `output_dir`

**File:** `config.py:105-140`

Added validation: `output_dir` must be a non-empty string. Added `test_catches_empty_output_dir` in `test_config.py`.

---

### M5: Silent failure when API returns empty answer text

**File:** `models.py:139-140`

`from_api_response()` now raises `ValueError` when the extracted answer text is empty. Added two tests: empty string content and missing `choices` key.

---

### M6: HTTP read timeout excessive for sync search

**File:** `researcher.py:63`

Reduced read timeout from 300 seconds to 60 seconds. Added an inline comment explaining the rationale.

---

### M7: `SearchResult` defaulted to empty strings for title and URL

**File:** `models.py:52-54`

`from_api_dict()` now logs a `WARNING` when title or URL is empty. Added `TestSearchResultWarnings` in `test_models.py` covering empty title, empty URL, missing title key, and the no-warning-for-valid-source case.

---

### M8: Domain error message used inconsistent terminology

**File:** `cli.py:156-159`

Changed "deny" to "exclude" in the mixed-domain `ValueError` message to match spec and help-text terminology.

---

### L1: Version string was hardcoded

**File:** `cli.py:33`

Replaced `_VERSION = "0.1.0"` with `_get_version()` using `importlib.metadata.version("deep-thought")` and a `PackageNotFoundError` fallback to `"unknown"`.

---

### L2: No roundtrip test for YAML frontmatter

**File:** `tests/research/test_output.py`

Added `test_yaml_roundtrip` to `TestBuildFrontmatter`: generates frontmatter, parses the YAML body with `yaml.safe_load()`, and verifies key fields. Includes a note that `yaml.safe_load` parses ISO timestamps as `datetime` objects.

---

### L3: `PerplexityClient` did not implement context manager protocol

**File:** `researcher.py:37-64`

Added `__enter__` (returns `self`) and `__exit__` (calls `self.close()`) methods so the client can be used in a `with` statement.

---

### L4: `Retry-After` header only handled integer seconds

**File:** `researcher.py:310-315`

Added a comment documenting that HTTP-date format is not supported and will fall back silently to exponential backoff.

---

### L5: `cost_usd` rendered without precision control

**File:** `output.py:77`

Formatted with `f"{result.cost_usd:.6f}".rstrip("0").rstrip(".")` to produce clean decimal output. Added `test_cost_formatted_with_precision` and `test_cost_strips_floating_point_noise` in `test_output.py`.

---

### L6: Logging setup happened after `--save-config`

**File:** `cli.py:500-505, 553-558`

Moved `_setup_logging()` to before the `--save-config` check in both `search_main()` and `research_main()` so logging is always configured before any code runs.
