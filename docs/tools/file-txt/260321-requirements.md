# Product Brief — File-Txt Tool

## Name and Purpose

**File-Txt Tool** — converts PDF, Office, and email files to markdown. With `--llm`, also generates `llms-full.txt` (full content) and `llms.txt` (index) optimized for LLM consumption.

## Processing Modes

1. **CLI Command** — `file-txt` (entry point)
2. **Default** — Convert input files to per-document markdown. (`file-txt path/`)
3. **LLM mode** — Same as default, plus aggregate `llms-full.txt` and `llms.txt` across all outputs. (`file-txt path/ --llm`)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **PyMuPDF4LLM** (`pymupdf4llm`) for PDF conversion — native text extraction, no ML models, no OCR.
3. **MarkItDown** (`markitdown`) for Office and HTML conversion (DOCX, PPTX, XLSX, HTML, HTM).
4. **extract-msg** ([`extract-msg`](https://github.com/TeamMsgExtractor/msg-extractor)) for OLE 2 compound document (.msg) parsing.
5. **html2text** ([`html2text`](https://github.com/Alir3z4/html2text)) for HTML email body conversion.
6. Standard library [`email`](https://docs.python.org/3.12/library/email.html) module for RFC 822 (.eml) parsing.
7. No state tracking.
8. No API keys or secrets.
9. Fully local processing.
10. A changelog is maintained in `files/tools/file-txt/CHANGELOG.md`.

## Command List

Running `file-txt` with no arguments displays usage information. Conversion is the default operation — no subcommand required.

| Subcommand         | Description                                           |
| ------------------ | ----------------------------------------------------- |
| `file-txt convert` | Convert files to markdown (same as default operation) |
| `file-txt config`  | Validate and display current YAML configuration       |
| `file-txt init`    | Create config file and directory structure            |

| Flag                     | Description                                                              |
| ------------------------ | ------------------------------------------------------------------------ |
| `PATH`                   | Input file or directory (positional; default: `input/`)                  |
| `--output PATH`          | Output directory (default: `output/`)                                    |
| `--llm`                  | Also generate `llms-full.txt` and `llms.txt` in the output root          |
| `--include-page-numbers` | Embed page numbers in markdown output (PDF only)                         |
| `--prefer-html`          | Prefer HTML body over plain text for email files (email only)            |
| `--full-headers`         | Include additional headers beyond From/To/Date (email only)              |
| `--include-attachments`  | Include attachment metadata in output (email only; default: from config) |
| `--extract-images`       | Extract embedded images to img/ subdirectories                           |
| `--nuke`                 | Delete input files after successful processing                           |
| `--dry-run`              | Preview what would be converted without writing any files                |
| `--verbose` / `-v`       | Detailed logging                                                         |
| `--config PATH`          | Override default config file path                                        |
| `--version`              | Show version and exit                                                    |

Boolean flags support `--no-*` variants (e.g., `--no-include-page-numbers`) to override config-level `true` values.

**Supported input extensions:** `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`, `.eml`, `.msg`

**Automatic exclusions:** Office lock files matching `~$*` and hidden files matching `.*` are skipped.

## File & Output Map

```
files/tools/file-txt/
├── 260321-requirements.md        # This document
├── CHANGELOG.md                  # Release history
└── ISSUES.md                     # Known issues and gaps

src/config/
└── file-txt-configuration.yaml   # Tool configuration

src/deep_thought/file_txt/
├── __init__.py
├── cli.py                        # CLI entry point and argument parsing
├── config.py                     # YAML config loader and validation
├── convert.py                    # Orchestrates conversion and output per file
├── filters.py                    # Extension, size, and exclude-pattern filtering
├── output.py                     # Markdown + YAML frontmatter generation
├── llms.py                       # llms-full.txt and llms.txt generation
├── image_extractor.py            # Image extraction to img/ subdirectory
└── engines/
    ├── __init__.py
    ├── email_utils.py            # Shared email conversion utilities
    ├── pymupdf_engine.py         # PyMuPDF4LLM PDF conversion
    ├── markitdown_engine.py      # MarkItDown conversion for Office/HTML
    ├── eml_engine.py             # RFC 822 .eml email conversion
    └── msg_engine.py             # OLE 2 .msg email conversion

output/                           # Default output root; override with --output
├── {document_name}/
│   ├── {document_name}.md        # Full markdown with YAML frontmatter
│   └── img/                      # Extracted images (if any)
│       └── image_001.png
├── llms-full.txt                 # All document content (generated with --llm)
└── llms.txt                      # Index and navigation (generated with --llm)
```

## Configuration

Configuration is stored in `src/config/file-txt-configuration.yaml`. All values below are required unless marked optional.

```yaml
# Email
prefer_html: false # true = convert HTML body; false = prefer plain text
full_headers: false # true = include all MIME headers
include_attachments: true

# Output
output_dir: "output/"
include_page_numbers: false
extract_images: true

# Limits
max_file_size_mb: 200

# File filter
allowed_extensions:
  - ".pdf"
  - ".docx"
  - ".pptx"
  - ".xlsx"
  - ".html"
  - ".htm"
  - ".eml"
  - ".msg"
exclude_patterns:
  - "~$*" # Office lock files
  - ".*" # Hidden files
```

## Data Format

### Markdown Output

Each input file produces one directory:

```
output/{document_name}/
├── {document_name}.md
└── img/
    └── image_001.png
```

Each markdown file includes YAML frontmatter:

```markdown
---
tool: file-txt
source_file: report.pdf
file_type: pdf
page_count: 42
word_count: 18340
has_images: true
processed_date: 2026-03-21T10:00:00Z
---

{document content}
```

For Office files, `page_count` is omitted; `file_type` reflects the source extension.

For email files, `page_count` is omitted and email-specific fields are added:

```markdown
---
tool: file-txt
source_file: message.eml
file_type: eml
from: "Sender Name <sender@example.com>"
to: "recipient@example.com"
subject: "Project Update"
date: "2026-03-15T09:30:00+00:00"
has_attachments: true
attachment_count: 2
word_count: 350
has_images: false
processed_date: 2026-03-22T10:00:00Z
---
```

Email markdown body structure:

```markdown
# Project Update

**From:** Sender Name <sender@example.com>
**To:** recipient@example.com
**Cc:** colleague@example.com
**Date:** 2026-03-15T09:30:00+00:00

---

Email body content here. Links are preserved as [text](url).

---

## Attachments

- `proposal.pdf` (245 KB)
- `budget.xlsx` (48 KB)
```

### llms-full.txt (--llm only)

One file in the output root. Each document is separated by a delimiter block:

```
# {Document Title or filename}

source: report.pdf
type: pdf
processed: 2026-03-21T10:00:00Z

{full markdown content of the document, frontmatter stripped}

---

# {Next Document}
...
```

### llms.txt (--llm only)

Index file in the output root, following the llmstxt.org convention:

```
# Document Index

> Processed by file-txt on 2026-03-21. {N} documents.

## Documents

- [{document_name}.md]({document_name}/{document_name}.md): {source filename}, {file_type}, {word_count} words
- [{document_name}.md]({document_name}/{document_name}.md): {source filename}, {file_type}, {word_count} words
```

**Implementation notes:**

- `llms.txt` and `llms-full.txt` are written to the output root after all documents are processed.
- If `--llm` is not passed, neither file is generated.
- Documents are ordered by processing sequence (input order / directory walk order).
- Frontmatter is stripped from content written into `llms-full.txt`.

## Claude Questions

1. **Subcommand for conversion?** No — conversion is the default operation triggered by `file-txt` directly. `config` and `init` are the only named subcommands. The `--llm` flag modifies the default operation's output.
2. **Per-document llms files or aggregate?** Aggregate — one `llms-full.txt` and one `llms.txt` per run, written to the output root. Per-document LLM files are not generated.
3. **Where is the output root?** Defaults to `output/` relative to the working directory; overridable with `--output`.
4. **Single PDF engine?** Yes — PyMuPDF4LLM only. Native text extraction; no OCR for scanned/image-only PDFs.
