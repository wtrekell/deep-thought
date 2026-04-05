# API, MCP, and SDK Documentation

## Table of Contents

- [API, MCP, and SDK Documentation](#api-mcp-and-sdk-documentation)
  - [Table of Contents](#table-of-contents)
  - [API](#api)
    - [Todoist API](#todoist-api)
    - [Perplexity API](#perplexity-api)
    - [Reddit API](#reddit-api)
    - [Gmail API](#gmail-api)
    - [Google Calendar API](#google-calendar-api)
    - [Google Drive API](#google-drive-api)
    - [Gemini API](#gemini-api)
  - [MCP](#mcp)
    - [Official MCP Servers](#official-mcp-servers)
      - [Todoist MCP](#todoist-mcp)
      - [Perplexity MCP](#perplexity-mcp)
      - [Playwright MCP](#playwright-mcp)
      - [MarkItDown MCP](#markitdown-mcp)
    - [Community MCP Servers](#community-mcp-servers)
      - [Reddit](#reddit)
      - [Google Workspace (Gmail + Calendar)](#google-workspace-gmail--calendar)
      - [Gemini](#gemini)
      - [Whisper (mlx-whisper / openai-whisper)](#whisper-mlx-whisper--openai-whisper)
  - [SDK](#sdk)
    - [Todoist SDK for Python](#todoist-sdk-for-python)
    - [PRAW (Python Reddit API Wrapper)](#praw-python-reddit-api-wrapper)
    - [Google API Python Client](#google-api-python-client)
    - [google-genai](#google-genai)
    - [mlx-whisper](#mlx-whisper)
    - [openai-whisper](#openai-whisper)
    - [pymupdf4llm](#pymupdf4llm)
    - [qdrant-client](#qdrant-client)
    - [mlx-embeddings](#mlx-embeddings)
    - [MarkItDown](#markitdown)
    - [Playwright](#playwright)

## API

### Todoist API

Used by the **todoist** tool for syncing tasks, projects, labels, sections, and comments.

- [Documentation](https://developer.todoist.com/api/v1/)
- REST API base URL: `https://api.todoist.com/api/v1/`
- Auth: Bearer token via `TODOIST_API_KEY` environment variable

### Perplexity API

Used by the **research** tool for web search (`search` command) and deep research (`research` command).

- [Documentation](https://docs.perplexity.ai/)
- Base URL: `https://api.perplexity.ai`
- Endpoints:
  - `/chat/completions` — synchronous search (fast, seconds)
  - `/v1/async/sonar` — async deep research job submission
  - `/async/chat/completions/{id}` — polling for async job results
- Auth: Bearer token via `PERPLEXITY_API_KEY` environment variable
- Default models: `sonar` (search), `sonar-deep-research` (research)

### Reddit API

Used by the **reddit** tool to collect submissions and comments from subreddits. Accessed indirectly through the PRAW SDK.

- [Reddit App Console](https://www.reddit.com/prefs/apps)
- [API Documentation](https://www.reddit.com/dev/api/)
- Auth: OAuth 2.0 client credentials (read-only, no Reddit account required)
- Credentials: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, user agent string
- Rate limit: 60 requests/minute (enforced by PRAW)

### Gmail API

Used by the **gmail** tool to list, fetch, and process emails.

- [Documentation](https://developers.google.com/gmail/api)
- Auth: OAuth 2.0 via `credentials.json` and `token.json` (stored in config directory)
- Scopes: read-only Gmail access

### Google Calendar API

Used by the **gcal** tool to list and fetch calendar events.

- [Documentation](https://developers.google.com/calendar/api)
- Auth: OAuth 2.0 via `credentials.json` and `token.json` (stored in config directory)
- Scopes: read-only Calendar access

### Google Drive API

Used by the **gdrive** tool to upload and manage files in Google Drive for offsite backup.

- [Documentation](https://developers.google.com/workspace/drive/api/reference/rest/v3)
- Auth: OAuth 2.0 via `credentials.json` and `token.json` (stored in config directory)
- Scopes: `drive.file` (read/write access limited to files created by the app)

### Gemini API

Used by the **gmail** tool's attachment extractor to parse non-text email attachments using a multimodal LLM.

- [Documentation](https://ai.google.dev/gemini-api/docs)
- Auth: API key via `GEMINI_API_KEY` environment variable
- Default model: `gemini-2.5-flash`

## MCP

No MCP servers are currently configured in this project. The following are available for future use.

### Official MCP Servers

#### Todoist MCP

Published and maintained by Doist (the company behind Todoist). TypeScript, actively maintained with 91 releases. The older `Doist/todoist-mcp` repo is deprecated and redirects here.

- [GitHub](https://github.com/Doist/todoist-ai)
- Stars: ~417
- Install: see repo README

#### Perplexity MCP

Published and maintained by Perplexity AI. Exposes four tools: `perplexity_search`, `perplexity_ask`, `perplexity_research`, and `perplexity_reason`.

- [GitHub](https://github.com/perplexityai/modelcontextprotocol)
- Stars: ~2,100
- Install: `npx -y @perplexity-ai/mcp-server`

#### Playwright MCP

Published and maintained by Microsoft. Uses Playwright's accessibility tree rather than screenshots, so no vision model is required. The most widely adopted MCP server in this list.

- [GitHub](https://github.com/microsoft/playwright-mcp)
- Stars: ~30,100
- Install: `npx -y @playwright/mcp@latest`

#### MarkItDown MCP

Ships as part of the main Microsoft MarkItDown repo under `packages/markitdown-mcp`. Exposes a single `convert_to_markdown(uri)` tool supporting HTTP/HTTPS, file, and data URIs. Designed for local use with trusted agents only — not intended to be exposed on a public network.

- [GitHub](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp)
- Stars: ~93,100 (parent repo)
- Install: available on PyPI as `markitdown-mcp`

### Community MCP Servers

#### Reddit

No official server. Best community options:
- [adhikasp/mcp-reddit](https://github.com/adhikasp/mcp-reddit) — ~384 stars, Python, read-focused
- [jordanburke/reddit-mcp-server](https://github.com/jordanburke/reddit-mcp-server) — supports fetching and posting
- [netixc/reddit-mcp-server](https://github.com/netixc/reddit-mcp-server) — explicitly uses PRAW

#### Google Workspace (Gmail + Calendar)

No fully official server. Google lists a [Workspace MCP extension](https://github.com/gemini-cli-extensions/workspace) in their `google/mcp` catalog, but that repo explicitly states it is "not an officially supported Google product." Google's fully-managed MCP servers (announced April 2026) cover Cloud infrastructure only — not Gmail or Calendar.

Best community options:
- [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) — ~2,000 stars, covers 12 Google services including Gmail and Calendar, OAuth 2.1, actively maintained. Strongest option overall.
- [nspady/google-calendar-mcp](https://github.com/nspady/google-calendar-mcp) — Calendar-only, multi-account, smart scheduling, can import events from images/PDFs.
- [aaronsb/google-workspace-mcp](https://github.com/aaronsb/google-workspace-mcp) — Gmail + Calendar + Drive bundle.

#### Gemini

No official server. Google's MCP catalog focuses on Cloud infrastructure; the Gemini CLI consumes MCP servers but Google has not published one that exposes Gemini as a callable service for other agents.

Best community options:
- [aliargun/mcp-server-gemini](https://github.com/aliargun/mcp-server-gemini) — ~248 stars, exposes Gemini 2.5 with thinking, vision, and embeddings. Published on npm as `mcp-server-gemini`.
- [eternnoir/aistudio-mcp-server](https://github.com/eternnoir/aistudio-mcp-server) — supports all Gemini 2.5 models, multimodal file processing, PDF-to-Markdown, image analysis, audio transcription.

#### Whisper (mlx-whisper / openai-whisper)

No official server from Apple's MLX team or OpenAI. Community options split across three approaches:

- Local / Apple Silicon: [kachiO/mlx-whisper-mcp](https://github.com/kachiO/mlx-whisper-mcp) — ~23 stars, uses `mlx-community/whisper-large-v3-turbo`, supports file path / base64 / YouTube URL input.
- Local / cross-platform: [jwulff/whisper-mcp](https://github.com/jwulff/whisper-mcp) — uses whisper.cpp, no Apple Silicon dependency.
- Cloud API: [arcaputo3/mcp-server-whisper](https://github.com/arcaputo3/mcp-server-whisper) — ~50 stars, calls the OpenAI transcription API (`whisper-1`, `gpt-4o-transcribe`) rather than running a local model.

## SDK

### Todoist SDK for Python

Used by the **todoist** tool. The official Python client for the Todoist REST API.

- [Documentation](https://doist.github.io/todoist-api-python/)
- [GitHub](https://github.com/Doist/todoist-api-python/)
- [API](https://developer.todoist.com/api/v1/)
- Package: `todoist-api-python>=3.0.0`

### PRAW (Python Reddit API Wrapper)

Used by the **reddit** tool. Handles authentication, rate limiting, and the comment tree API.

- [Documentation](https://praw.readthedocs.io/)
- [GitHub](https://github.com/praw-dev/praw)
- Package: `praw>=7.7.1`

### Google API Python Client

Used by the **gmail**, **gcal**, and **gdrive** tools. The standard Python client for all Google REST APIs.

- [Documentation](https://googleapis.github.io/google-api-python-client/)
- [GitHub](https://github.com/googleapis/google-api-python-client)
- Packages:
  - `google-api-python-client>=2.0.0`
  - `google-auth-oauthlib>=1.0.0`
  - `google-auth-httplib2>=0.2.0`

### google-genai

Used by the **gmail** tool's attachment extractor to call the Gemini API. Replaces the deprecated `google-generativeai` package.

- [Documentation](https://ai.google.dev/gemini-api/docs/sdks)
- [GitHub](https://github.com/googleapis/python-genai)
- Package: `google-genai>=1.0.0`

### mlx-whisper

Used by the **audio** tool as the default transcription engine on Apple Silicon. Loads models from mlx-community on HuggingFace.

- [GitHub](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
- [HuggingFace models](https://huggingface.co/mlx-community)
- Package: `mlx-whisper>=0.4.0`
- Supported models: `tiny`, `base`, `small`, `medium`, `large-v3`

### openai-whisper

Optional transcription engine for the **audio** tool. Cross-platform fallback when MLX is unavailable.

- [GitHub](https://github.com/openai/whisper)
- Package: `openai-whisper` (optional dependency, install with `uv sync --extra whisper`)
- Default model: `large-v3-turbo`

### pymupdf4llm

Used by the **file-txt** tool to convert PDF files to markdown. Built on PyMuPDF — fast native text extraction, no ML models, no OCR.

- [Documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [GitHub](https://github.com/pymupdf/PyMuPDF)
- Package: `pymupdf4llm>=0.0.17`

### qdrant-client

Used by the **reddit**, **web**, and **research** tools to write document embeddings to the local Qdrant vector store. Optional — only required when running with embedding support enabled.

- [Documentation](https://python-client.qdrant.tech/)
- [GitHub](https://github.com/qdrant/qdrant-client)
- Package: `qdrant-client>=1.9.0` (optional extra: `uv sync --extra embeddings`)

### mlx-embeddings

Used by the **reddit**, **web**, and **research** tools to generate document embeddings on Apple Silicon. Loads `mlx-community/bge-small-en-v1.5-bf16` from HuggingFace. Optional — only required when running with embedding support enabled.

- [GitHub](https://github.com/Blaizzy/mlx-embeddings)
- Package: `mlx-embeddings>=0.1.0` (optional extra: `uv sync --extra embeddings`)

### MarkItDown

Used by the **file-txt** tool to convert Office documents (`.docx`, `.pptx`, `.xlsx`) and HTML to markdown.

- [GitHub](https://github.com/microsoft/markitdown)
- Package: `markitdown>=0.1.0`
- Supported formats: `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`, `.eml`

### Playwright

Used by the **web** tool's crawler to render JavaScript-heavy pages and extract content via a headless browser.

- [Documentation](https://playwright.dev/python/)
- [GitHub](https://github.com/microsoft/playwright-python)
- Package: `playwright>=1.40.0`
