# Reddit Tool

Rule-based collection of Reddit posts and comments via PRAW with rate-limit retry and LLM-optimized markdown export.

## Overview

The Reddit Tool authenticates with the Reddit API (PRAW), collects posts and comments matching configured rules, applies filters (score, age, keyword, flair, etc.), generates LLM-optimized markdown, optionally writes embeddings to Qdrant, and stores metadata in SQLite. Designed for harvesting Reddit communities into searchable knowledge bases.

## Data Flow

```
Reddit API (PRAW) → Rules → Filters → Markdown Export → [Optional: Embeddings to Qdrant] → SQLite DB
                        ↑
                Rate-limit Retry/Backoff
```

## Setup

1. Create a Reddit app and add credentials to `.env` at the project root:

   ```
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USER_AGENT=your_user_agent
   ```

2. Configure which subreddits and rules to use in `src/config/reddit-configuration.yaml`.

3. Initialize the database:

   ```bash
   reddit init
   ```

4. Collect posts:

   ```bash
   reddit
   ```

   Or run a specific rule:

   ```bash
   reddit --rule my_rule_name
   ```

## Configuration

Configuration lives at `src/config/reddit-configuration.yaml`. Key settings:

- **rules** — List of collection rules (each with a name, subreddit, sort method, and filters)
- **filters** — Global filters (score threshold, age, keywords, flair, stickied/locked, etc.)
- **include_images** — Download post images to `img/` directory
- **include_comments** — Collect top-level comments (optional)
- **embeddings** — Enable/disable Qdrant embedding writes

## Module Structure

| Module | Role |
| --- | --- |
| `cli.py` | CLI entry point with argparse subcommands |
| `client.py` | PRAW wrapper with authenticated session management |
| `config.py` | YAML config loader with Reddit credential resolution |
| `models.py` | Local dataclasses for posts, comments, and metadata |
| `processor.py` | Rule engine: fetch posts → apply filters → retry on rate-limit → export → DB write |
| `filters.py` | Meta-based filter engine (score, age, keyword, flair, locked, stickied) |
| `output.py` | Markdown generation with Reddit metadata, YAML frontmatter, and word counts |
| `image_extractor.py` | Downloads post images and thumbnails to local `img/` directory |
| `embeddings.py` | Writes post embeddings to Qdrant vector store |
| `utils.py` | Shared utilities (slugification, date handling) |
| `db/` | SQLite schema, migrations, and query functions |

## Data Storage

All paths are rooted at `data/reddit/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **SQLite database** — `<data_dir>/reddit.db` (canonical store)
- **Markdown export** — `<data_dir>/export/<subreddit>/<post_id>.md`
- **Post images** — `<data_dir>/export/<subreddit>/img/<post_id>/`
- **Embeddings** — Written to Qdrant at `localhost:6333`; collection name set by `qdrant_collection` in `reddit-configuration.yaml` (default: `deep_thought_documents`)

## Tool-Specific Notes

- **Rate-limit handling:** Automatic backoff with exponential retry (max 3 attempts); respects Reddit's 60-request/min limit
- **Rule-based collection:** Each rule specifies a subreddit, sort method (hot, new, top), and optional time window
- **Filter engine:** Stateless rule evaluation; supports score, age, keywords, flair, locked/stickied status
- **Image extraction:** Enabled via `include_images: true`; downloads post images and thumbnails
- **Comments:** Optional collection of top-level comments with separate YAML metadata
- **Embedding:** Requires MLX embeddings (optional extra) and Qdrant running at `localhost:6333`
- **Markdown frontmatter:** Posts include subreddit, author, score, timestamp, and filter metadata
