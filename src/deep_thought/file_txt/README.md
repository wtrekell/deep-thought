# File-Txt Tool

Converts PDF and Office documents (DOCX, PPTX, XLSX, HTML, EML, MSG) to LLM-optimized markdown.

## Overview

The file-txt tool ingests local files in various formats, converts them to clean markdown, optionally extracts embedded images, and can generate aggregate LLM-friendly output files. No OCR is performed — only native text extraction is used. Useful for bulk-converting document collections for prompt engineering or knowledge base population.

## Data Flow

```
Input file (PDF/Office/email) → Engine (pymupdf/markitdown/email) → Markdown output
                                                                           ↓
                                                              LLM aggregates (--llm flag, optional)
```

There is no SQLite layer. Converted markdown is written directly to the output directory.

## Setup

1. Configure input settings and output directory in `src/config/file-txt-configuration.yaml`.

2. Initialize the output directory and write the default config:

   ```bash
   file-txt init
   ```

3. Convert a directory or specific file:

   ```bash
   file-txt /path/to/documents
   ```

## CLI Commands

```
file-txt PATH [flags]          Convert files at PATH to markdown (default operation)
file-txt convert PATH [flags]  Explicit convert subcommand (same as above)
file-txt config                Validate and display the current configuration
file-txt init                  Write default config and create the output directory
```

### Convert flags

| Flag                                                   | Description                                               |
| ------------------------------------------------------ | --------------------------------------------------------- |
| `--output PATH`                                        | Override the output directory from config                 |
| `--llm`                                                | Also write `llms-full.txt` and `llms.txt` aggregate files |
| `--include-page-numbers` / `--no-include-page-numbers` | Retain page markers in PDF output                         |
| `--extract-images` / `--no-extract-images`             | Extract embedded images to `img/` subdirectories          |
| `--prefer-html` / `--no-prefer-html`                   | For email: prefer HTML body over plain text               |
| `--full-headers` / `--no-full-headers`                 | For email: include all headers beyond From/To/Date        |
| `--include-attachments` / `--no-include-attachments`   | For email: include attachment metadata                    |
| `--nuke`                                               | Delete source files after successful conversion           |
| `--dry-run`                                            | Show what would be converted without writing files        |
| `--config PATH`                                        | Override the config file path                             |
| `--verbose` / `-v`                                     | Increase log output                                       |

## Configuration

Configuration lives at `src/config/file-txt-configuration.yaml`. The file is flat — all keys are at the top level, grouped by concern.

### Email settings

| Key                   | Default | Description                                      |
| --------------------- | ------- | ------------------------------------------------ |
| `prefer_html`         | `false` | Prefer HTML body over plain text when both exist |
| `full_headers`        | `false` | Include all MIME headers in output               |
| `include_attachments` | `true`  | List attachments in email conversion output      |

### Output settings

| Key                    | Default     | Description                                      |
| ---------------------- | ----------- | ------------------------------------------------ |
| `output_dir`           | `"output/"` | Directory for converted markdown files           |
| `include_page_numbers` | `false`     | Retain page number markers in PDF output         |
| `extract_images`       | `true`      | Extract and save images to `img/` subdirectories |

### Limits

| Key                | Default | Description                                         |
| ------------------ | ------- | --------------------------------------------------- |
| `max_file_size_mb` | `200`   | Skip files larger than this threshold (must be > 0) |

### File filter

| Key                  | Default              | Description                                         |
| -------------------- | -------------------- | --------------------------------------------------- |
| `allowed_extensions` | `[.pdf, .docx, ...]` | Extensions to process; must have at least one entry |
| `exclude_patterns`   | `["~$*", ".*"]`      | Glob patterns for files to skip                     |

## Output Structure

All output is written to `output_dir` (default: `output/`). Override with `--output` at the CLI.

- **Converted markdown** — `<output_dir>/<filename>.md`
- **Extracted images** — `<output_dir>/img/<filename>/`
- **LLM full context** — `<output_dir>/llms-full.txt` (all docs concatenated, requires `--llm`)
- **LLM index** — `<output_dir>/llms.txt` (document index with word counts, requires `--llm`)

## Module Structure

| Module                         | Role                                                          |
| ------------------------------ | ------------------------------------------------------------- |
| `cli.py`                       | CLI entry point: `convert`, `config`, `init` subcommands      |
| `config.py`                    | YAML config loader with flat key parsing                      |
| `convert.py`                   | Dispatcher: routes each file to the appropriate engine        |
| `engines/pymupdf_engine.py`    | PDF text extraction via pymupdf4llm                           |
| `engines/markitdown_engine.py` | Office/HTML conversion via markitdown                         |
| `engines/eml_engine.py`        | EML email parsing and conversion                              |
| `engines/msg_engine.py`        | Outlook MSG file handling                                     |
| `engines/email_utils.py`       | Shared email parsing utilities                                |
| `filters.py`                   | Input file discovery and filtering                            |
| `image_extractor.py`           | Extracts and saves embedded images                            |
| `output.py`                    | Markdown file writing                                         |
| `llms.py`                      | Aggregates converted docs into `llms-full.txt` and `llms.txt` |

## Tool-Specific Notes

- **No OCR:** Only extractable text is converted; scanned PDFs without text layers are skipped
- **No database:** file-txt has no SQLite layer — output is written directly to the filesystem
- **Email handling:** EML and MSG files are parsed to extract body text, headers, and attachment metadata
- **Image extraction:** Enabled via `extract_images: true` in config or `--extract-images` flag; images are saved with sanitized filenames
- **Size limits:** Files larger than `max_file_size_mb` are skipped to avoid memory overhead
- **Exit codes:** `0` = all ok, `1` = all failed, `2` = partial failure (some converted, some errored)
