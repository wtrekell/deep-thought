# Product Brief — File-Txt Tool

## Name and Purpose

**File-Txt Tool** — converts PDF and Office documents to markdown. With `--llm`, also generates `llms-full.txt` (full content) and `llms.txt` (index) optimized for LLM consumption.

## Processing Modes

1. **CLI Command** — `file-txt` (entry point)
2. **Default** — Convert input files to per-document markdown. (`file-txt path/`)
3. **LLM mode** — Same as default, plus aggregate `llms-full.txt` and `llms.txt` across all outputs. (`file-txt path/ --llm`)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **Marker** (`marker-pdf`) for PDF conversion — fully local, no API key required.
3. **MarkItDown** (`markitdown`) for Office and HTML conversion (DOCX, PPTX, XLSX, HTML, HTM).
4. No state tracking.
5. No API keys or secrets.
6. Fully local processing.
7. A changelog is maintained in `files/tools/file-txt/CHANGELOG.md`.

## Command List

Running `file-txt` with no arguments shows help. Conversion is the default operation — no subcommand required.

| Subcommand        | Description                                     |
| ----------------- | ----------------------------------------------- |
| `file-txt config` | Validate and display current YAML configuration |
| `file-txt init`   | Create config file and directory structure      |

| Flag                     | Description                                                     |
| ------------------------ | --------------------------------------------------------------- |
| `PATH`                   | Input file or directory (positional; default: `input/`)         |
| `--output PATH`          | Output directory (default: `output/`)                           |
| `--llm`                  | Also generate `llms-full.txt` and `llms.txt` in the output root |
| `--force-ocr`            | Force OCR on all pages regardless of content (PDF only)         |
| `--torch-device TEXT`    | Torch device: `mps`, `cuda`, or `cpu` (PDF only; default: `mps`) |
| `--include-page-numbers` | Embed page numbers in markdown output (PDF only)                |
| `--nuke`                 | Delete input files after successful processing                  |
| `--dry-run`              | Preview what would be converted without writing any files       |
| `--verbose` / `-v`       | Detailed logging                                                |
| `--config PATH`          | Override default config file path                               |
| `--save-config PATH`     | Write example config to path and exit                           |
| `--version`              | Show version and exit                                           |

**Supported input extensions:** `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`

**Automatic exclusions:** Office lock files matching `~$*` and hidden files matching `.*` are skipped.

## File & Output Map

```
files/tools/file-txt/
├── 260321-requirements.md        # This document
└── CHANGELOG.md                  # Release history

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
    ├── marker_engine.py          # Marker PDF conversion
    └── markitdown_engine.py      # MarkItDown conversion for Office/HTML

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
# Marker (PDF)
force_ocr: false
torch_device: "mps"             # 'mps', 'cuda', or 'cpu'

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
exclude_patterns:
  - "~$*"                       # Office lock files
  - ".*"                        # Hidden files
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
4. **Single PDF engine?** Yes — Marker only. Speed difference vs. PyMuPDF4LLM is irrelevant for short documents; Marker produces better quality output.

