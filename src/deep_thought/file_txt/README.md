# File-Txt Tool

Converts PDF and Office documents (DOCX, PPTX, XLS, MSG, EML) to LLM-optimized markdown.

## Overview

The File-Txt Tool ingests local files in various formats, converts them to clean markdown, extracts embedded images, and optionally generates aggregate LLM-friendly summary files. No OCR is performed — only native text extraction is used. Useful for bulk-converting document collections for prompt engineering or knowledge base population.

## Data Flow

```
Input File (PDF/Office) → Engine (pymupdf/markitdown/email) → Image Extraction → Markdown Export
                                                                          ↓
                                                                    LLM aggregates (optional)
```

## Setup

1. Configure which file types and directories to process in `src/config/file-txt-configuration.yaml`.

2. Initialize the output directory:

   ```bash
   file-txt config init
   ```

3. Convert a directory or specific file:

   ```bash
   file-txt /path/to/documents
   ```

## Configuration

Configuration lives at `src/config/file-txt-configuration.yaml`. Key settings:

- **input** — Root directory to scan for files
- **output** — Where to write markdown and images
- **include_images** — Whether to extract and save embedded images
- **llm_aggregation** — Generate `llm-full.txt` (all docs) and `llm.txt` (summary) for LLM context
- **skip_patterns** — Glob patterns to exclude (e.g., `*.bak`, `node_modules`)
- **max_file_size_mb** — Skip files larger than this threshold

## Module Structure

| Module | Role |
| --- | --- |
| `cli.py` | CLI entry point with argparse subcommands |
| `config.py` | YAML config loader with .env integration |
| `convert.py` | Dispatcher: routes each file to appropriate engine, returns ConvertResult |
| `engines/pymupdf_engine.py` | PDF text extraction via pymupdf4llm |
| `engines/markitdown_engine.py` | Office/HTML conversion via markitdown |
| `engines/eml_engine.py` | Email (EML) parsing and conversion |
| `engines/msg_engine.py` | Outlook message (MSG) file handling |
| `engines/email_utils.py` | Shared email parsing utilities |
| `filters.py` | Input file discovery and filtering |
| `image_extractor.py` | Extracts and saves embedded images |
| `output.py` | Markdown file writing and LLM aggregation |
| `llms.py` | Aggregates converted docs into LLM-friendly summary files |

## Data Storage

All paths are rooted at `data/file-txt/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **Markdown export** — `<data_dir>/export/<filename>.md`
- **Extracted images** — `<data_dir>/export/img/<filename>/`
- **LLM aggregates** — `<data_dir>/export/llm-full.txt`, `llm.txt` (optional)

## Tool-Specific Notes

- **No OCR:** Only extractable text is converted; scanned PDFs without text layers are skipped
- **Email handling:** EML and MSG files are parsed to extract body text, headers, and attachments
- **Image extraction:** Enabled via `include_images: true`; images are saved with sanitized filenames
- **Size limits:** Large files can be skipped to avoid memory overhead; configurable per document type
