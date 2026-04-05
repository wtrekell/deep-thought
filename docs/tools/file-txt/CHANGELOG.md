# file-txt Changelog

## 0.3.0 — 2026-04-02

### Changed

- **Replaced `marker-pdf` with `pymupdf4llm`** for PDF conversion. `pymupdf4llm` uses PyMuPDF (fitz) to extract markdown from native PDFs — no ML models, no GPU, no transformers dependency.
- `MarkerConfig` dataclass replaced by `PdfConfig` (no fields); `FileTxtConfig.marker` field renamed to `FileTxtConfig.pdf`.
- `_parse_marker_config` config helper replaced by `_parse_pdf_config`.
- `engines/marker_engine.py` replaced by `engines/pymupdf_engine.py`.

### Removed

- `force_ocr` config key and `--force-ocr` CLI flag (OCR on scanned PDFs is not supported by pymupdf4llm).
- `torch_device` config key, `--torch-device` CLI flag, and `torch_device` validation (no device selection needed — pymupdf4llm has no model).
- `include_page_numbers` option for the PDF path (pymupdf4llm does not inject page number markers).
- Model loading / caching logic that was specific to marker-pdf.
- `transformers` and all other marker-pdf transitive dependencies are no longer installed.

### Why

`marker-pdf` requires `transformers<5.0.0`; `mlx-embeddings` (in the `[embeddings]` extra) requires `transformers>=5.0.0`. The conflict caused an import failure (`No module named 'transformers.onnx'`) at runtime. `pymupdf4llm` has no ML dependencies and eliminates the conflict entirely.

## 0.2.0 — 2026-03-22

### Added

- **Email support**: `.eml` (RFC 822) and `.msg` (OLE 2) files are now converted to markdown with email-specific frontmatter fields (`from`, `to`, `subject`, `date`, `has_attachments`, `attachment_count`).
- EML engine using stdlib `email` module for parsing.
- MSG engine using `extract-msg` library for parsing.
- Shared email utility module (`engines/email_utils.py`) with `convert_html_to_markdown`, `format_file_size`, and `build_email_markdown`.
- `EmailConfig` dataclass with `prefer_html`, `full_headers`, and `include_attachments` fields.
- CLI flags: `--prefer-html`, `--full-headers`, `--include-attachments` for email conversion control.
- CLI flag: `--extract-images` / `--no-extract-images` to control image extraction from the command line.
- All boolean CLI flags now support `--no-*` variants via `BooleanOptionalAction` to override config-level `true` values (e.g., `--no-force-ocr`).
- Config validation is now called during conversion, not just via `file-txt config`.
- Unknown YAML configuration keys now emit a warning to help catch typos.
- Output name collision detection: files with the same stem but different extensions (e.g., `report.pdf` and `report.docx`) now produce separate output directories instead of silently overwriting.
- Marker PDF engine caches model dict and converter across calls for batch performance.
- `--torch-device` now validates against `mps`, `cuda`, `cpu` choices at the CLI level.
- Dynamic version from package metadata instead of hardcoded string.
- Unrecognized CLI arguments now produce a warning when a subcommand is specified.
- EML engine captures inline attachments with filenames (e.g., inline images).
- `convert` subcommand documented in requirements alongside the default no-subcommand mode.
- `extract-msg>=0.50.0` added as a project dependency.
- Comprehensive test suites: `test_cli.py` (23 tests), `test_image_extractor.py` (12 tests), plus 25 new tests across existing test files.

### Fixed

- YAML frontmatter injection: email metadata values containing double quotes are now escaped.
- EML date parsing crash on malformed date headers — now falls back to the raw string with a warning.
- MSG engine body extraction used falsy check instead of `None` check, causing empty-string bodies to incorrectly fall through to HTML conversion.
- Base64 image decoding crash in `image_extractor.py` — malformed data now leaves the original markdown unchanged instead of aborting all image extraction.
- SVG images (`image/svg+xml`) were silently ignored by the base64 image regex due to `+` not being in the character class.
- Dead `--save-config` flag on the `convert` subcommand removed (it only belongs on `init`).
- `_strip_frontmatter` promoted from private to public API in `llms.py`, removing the `noqa` suppression.
- `_PROJECT_ROOT` path resolution now uses `Path.resolve()` and traverses the correct number of levels, improving reliability in editable installs.
- Python fallback default for `torch_device` changed from `cpu` to `mps` to match the shipped YAML config.
- `_EXTERNAL_IMAGE_PATTERN` dead code removed from `image_extractor.py`.
- `--full-headers` help text updated to accurately describe behavior for both EML (all MIME headers) and MSG (Message-ID and In-Reply-To) engines.
- Requirements doc updated: added Cc line to email body example, corrected no-args behavior description, added `convert` subcommand, added `--extract-images` flag, documented `--no-*` variants.
- ImportError in html2text conversion is now re-raised instead of being silently swallowed by a broad `except Exception`.

## 0.1.0 — 2026-03-21

### Added

- Initial release of the file-txt tool.
- PDF conversion via Marker engine.
- Office and HTML conversion via MarkItDown engine (DOCX, PPTX, XLSX, HTML, HTM).
- YAML frontmatter generation with document metadata.
- Image extraction from base64-embedded images to `img/` subdirectories.
- LLM aggregate output (`llms-full.txt` and `llms.txt`) with `--llm` flag.
- YAML configuration with Marker, output, limits, and filter sections.
- CLI subcommands: `config` (validate and display) and `init` (create config and directories).
- File filtering by extension allowlist, exclusion patterns, and size limits.
- `--force-ocr`, `--torch-device`, `--include-page-numbers` PDF flags.
- `--nuke` flag for deleting source files after successful conversion.
- `--dry-run` flag for previewing conversion without writing files.
