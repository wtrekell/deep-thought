# Research Tool — Known Issues

Issues identified during code review on 2026-03-23. Severity ratings: medium, low.

---

## Medium Severity

### M1: `to_frontmatter_dict()` is dead code

**File:** `models.py:169-199`

`ResearchResult.to_frontmatter_dict()` is defined and tested but never called anywhere. The `output.py` module builds frontmatter directly via `_build_frontmatter()` using string concatenation. This creates two separate representations of the same output logic that can diverge.

**Recommendation:** Either use `to_frontmatter_dict()` inside `_build_frontmatter()` as the source of truth, or remove the method and its tests.

---

### M2: No markdown escaping for source titles and snippets

**File:** `output.py:119-127`

Source titles and snippets are rendered directly into markdown link syntax without escaping. If a title contains markdown special characters (e.g., `[brackets]`, `*asterisks*`), the rendered markdown link becomes malformed.

**Recommendation:** Add a helper to escape markdown special characters in titles and snippets before rendering them into `[title](url)` syntax.

---

### M3: Config loading silently applies defaults for required fields

**File:** `config.py:95-101`

The spec states all config values except `default_recency` are required. However, `load_config()` uses `.get()` with hardcoded defaults for every field. A malformed config with missing keys silently uses defaults instead of alerting the user.

**Recommendation:** Use direct key access (e.g., `raw_dict["api_key_env"]`) for required fields so that a missing key raises `KeyError` with a clear message.

---

### M4: Config validation does not check `output_dir`

**File:** `config.py:105-140`

`validate_config()` checks `api_key_env`, `search_model`, `research_model`, retry settings, and `default_recency`, but does not validate that `output_dir` is a non-empty string. An empty `output_dir` would cause confusing errors at file-write time.

**Recommendation:** Add validation: `output_dir` must be a non-empty string.

---

### M5: Silent failure when API returns empty answer text

**File:** `models.py:139-140`

`ResearchResult.from_api_response()` defaults to an empty string if `choices[0].message.content` is missing. A malformed API response produces a result with an empty answer rather than raising an error.

**Recommendation:** Validate that the answer text is non-empty and raise `ValueError` if the API returned no content.

---

### M6: HTTP read timeout excessive for sync search

**File:** `researcher.py:63`

The httpx client uses `timeout=httpx.Timeout(30.0, read=300.0)` — a 5-minute read timeout. For the `search` command (typical 2-10 seconds), this is excessive. If the API hangs after sending headers, the client waits 5 minutes before timing out.

**Recommendation:** Use a tighter read timeout (e.g., 60 seconds). The async `research` command has its own 10-minute polling timeout, so individual requests don't need 5 minutes.

---

### M7: `SearchResult` defaults to empty strings for title and URL

**File:** `models.py:52-54`

`SearchResult.from_api_dict()` defaults `title` and `url` to empty strings via `.get("title", "")`. An empty title or URL makes the source citation unusable in the markdown output but is silently accepted.

**Recommendation:** Log a warning when title or URL is empty, or use fallback values like `"(untitled)"` / `"(missing url)"`.

---

### M8: Domain error message uses inconsistent terminology

**File:** `cli.py:156-159`

The error message for mixed domain types says "deny" while the spec and help text use "exclude." Minor terminology mismatch.

**Recommendation:** Change "deny" to "exclude" for consistency with spec language.

---

## Low Severity

### L1: Version string is hardcoded

**File:** `cli.py:33`

`_VERSION = "0.1.0"` is a hardcoded module constant that must be manually kept in sync with `pyproject.toml`. If the package version is bumped, the CLI version will be stale.

**Recommendation:** Use `importlib.metadata.version("deep-thought")` to read the version from package metadata at runtime.

---

### L2: No roundtrip test for YAML frontmatter

**File:** `tests/research/test_output.py`

Tests verify that frontmatter is generated with expected content, but no test parses the generated YAML back with `yaml.safe_load()` to verify it is syntactically valid. Subtle escaping bugs could produce invalid YAML that string assertions miss.

**Recommendation:** Add a roundtrip test: generate frontmatter, extract the YAML between `---` delimiters, parse with `yaml.safe_load()`, and verify key fields match.

---

### L3: PerplexityClient does not implement context manager protocol

**File:** `researcher.py:37-64`

The class docstring says "use it as a context manager" but `__enter__` and `__exit__` are not implemented. Callers must use `try/finally` with `close()`.

**Recommendation:** Add `__enter__` and `__exit__` methods so the client can be used with `with` statements.

---

### L4: Retry-After header only handles integer seconds

**File:** `researcher.py:310-315`

The retry logic parses `Retry-After` as `float()` only. Per RFC 7231, this header can also be an HTTP-date string, which would fail `float()` conversion and silently fall back to exponential backoff.

**Recommendation:** Add HTTP-date parsing as a fallback, or document that date-format headers are not supported.

---

### L5: `cost_usd` rendered without precision control

**File:** `output.py:77`

The cost field is rendered as a raw float (e.g., `0.006000000000000001`). Very small or floating-point-imprecise costs produce unwieldy frontmatter values.

**Recommendation:** Format with fixed precision (e.g., `f"{result.cost_usd:.6f}"`) and strip trailing zeros.

---

### L6: Logging setup happens after --save-config

**File:** `cli.py:500-505, 553-558`

`_setup_logging()` is called after `--save-config` is handled. If `--save-config` is used, logging is never configured. While `--save-config` exits immediately, any errors during config writing are not logged.

**Recommendation:** Move `_setup_logging()` to before the `--save-config` check.
