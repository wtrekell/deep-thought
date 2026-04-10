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

1. Create a Reddit app and add credentials to `.env` at the project root (or store in macOS Keychain under service `deep-thought-reddit`):

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

   Or run a specific rule, preview without writing, or force a full reprocess:

   ```bash
   reddit --rule my_rule_name
   reddit --dry-run
   reddit --force
   ```

## CLI Reference

```
reddit [--config PATH] [--rule NAME] [--output PATH] [--dry-run] [--force] [--verbose]
reddit init
reddit config [--config PATH]
reddit --save-config PATH
```

| Flag / Subcommand    | Description                                                 |
| -------------------- | ----------------------------------------------------------- |
| _(no subcommand)_    | Run collection according to configured rules                |
| `init`               | Create the database, config file, and directory structure   |
| `config`             | Validate and display the current YAML configuration         |
| `--rule NAME`        | Run only the named rule (default: all rules)                |
| `--output PATH`      | Override the output directory from configuration            |
| `--config PATH`      | Override the default configuration file path                |
| `--dry-run`          | Preview what would be collected without writing any files   |
| `--force`            | Clear per-post state and reprocess all matching posts       |
| `--verbose` / `-v`   | Increase log output to DEBUG level                          |
| `--save-config PATH` | Write a default example configuration file to PATH and exit |

## Configuration

Configuration lives at `src/config/reddit-configuration.yaml`. Top-level settings:

| Field               | Type   | Default                | Description                                          |
| ------------------- | ------ | ---------------------- | ---------------------------------------------------- |
| `client_id_env`     | string | `REDDIT_CLIENT_ID`     | Env var name holding the Reddit app client ID        |
| `client_secret_env` | string | `REDDIT_CLIENT_SECRET` | Env var name holding the Reddit app client secret    |
| `user_agent_env`    | string | `REDDIT_USER_AGENT`    | Env var name holding the Reddit user agent string    |
| `max_posts_per_run` | int    | `500`                  | Global cap across all rules per invocation           |
| `output_dir`        | string | `data/reddit/export/`  | Directory for exported markdown files                |
| `qdrant_collection` | string | `deep_thought_db`      | Qdrant collection to write embeddings into           |
| `rules`             | list   | —                      | List of collection rules (see per-rule fields below) |

### Per-Rule Fields

Each entry under `rules` supports:

| Field                | Type         | Default  | Description                                                        |
| -------------------- | ------------ | -------- | ------------------------------------------------------------------ |
| `name`               | string       | required | Unique rule name; used as output subdirectory                      |
| `subreddit`          | string       | required | Subreddit name without the `r/` prefix                             |
| `sort`               | string       | `hot`    | Fetch order: `new`, `hot`, `top`, `rising`                         |
| `time_filter`        | string       | `week`   | For `top` sort: `hour`, `day`, `week`, `month`, `year`, `all`      |
| `limit`              | int          | `25`     | Submissions to fetch per rule run                                  |
| `min_score`          | int          | `0`      | Minimum upvote score threshold                                     |
| `min_comments`       | int          | `0`      | Minimum comment count threshold                                    |
| `max_age_days`       | int          | `7`      | Maximum post age in days                                           |
| `include_keywords`   | list[string] | `[]`     | Post must match at least one (supports `*` and `?` glob wildcards) |
| `exclude_keywords`   | list[string] | `[]`     | Post must not match any of these                                   |
| `include_flair`      | list[string] | `[]`     | Only collect posts with these flair values (empty = all)           |
| `exclude_flair`      | list[string] | `[]`     | Skip posts with these flair values                                 |
| `search_comments`    | bool         | `false`  | Also match keywords against comment bodies                         |
| `max_comment_depth`  | int          | `3`      | Maximum comment nesting depth to collect                           |
| `max_comments`       | int          | `200`    | Maximum comments to collect per post                               |
| `include_images`     | bool         | `false`  | Download post images to `img/` directory                           |
| `exclude_stickied`   | bool         | `false`  | Skip mod-pinned posts                                              |
| `exclude_locked`     | bool         | `false`  | Skip posts that can no longer receive comments                     |
| `replace_more_limit` | int or null  | `32`     | MoreComments nodes to expand per post (0 = none, null = all)       |

## Module Structure

| Module               | Role                                                                               |
| -------------------- | ---------------------------------------------------------------------------------- |
| `cli.py`             | CLI entry point with argparse subcommands                                          |
| `client.py`          | PRAW wrapper with authenticated session management                                 |
| `config.py`          | YAML config loader with Reddit credential resolution                               |
| `models.py`          | Local dataclasses for posts, comments, and metadata                                |
| `processor.py`       | Rule engine: fetch posts → apply filters → retry on rate-limit → export → DB write |
| `filters.py`         | Meta-based filter engine (score, age, keyword, flair, locked, stickied)            |
| `output.py`          | Markdown generation with Reddit metadata, YAML frontmatter, and word counts        |
| `image_extractor.py` | Downloads post images to local `img/` directory                                    |
| `embeddings.py`      | Writes post embeddings to Qdrant vector store                                      |
| `utils.py`           | Shared utilities (slugification, date handling)                                    |
| `db/`                | SQLite schema, migrations, and query functions                                     |

## Data Storage

All paths are rooted at `data/reddit/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **SQLite database** — `<data_dir>/reddit.db` (canonical store)
- **Markdown export** — `<data_dir>/export/<rule_name>/<post_id>.md`
- **Post images** — `<data_dir>/export/<rule_name>/img/<post_id>/`
- **Embeddings** — Written to Qdrant at `localhost:6333`; collection name set by `qdrant_collection` in `reddit-configuration.yaml` (default: `deep_thought_db`)

## Tool-Specific Notes

- **Credentials:** Keychain is checked first (service `deep-thought-reddit`), with `.env` as fallback
- **Rate-limit handling:** Automatic backoff with exponential retry (max 3 attempts); respects Reddit's 60-request/min limit
- **Rule-based collection:** Each rule specifies a subreddit, sort method, and optional filters — all filter fields are per-rule, not global
- **Filter engine:** Stateless rule evaluation; supports score, age, keywords, flair, locked/stickied status
- **Image extraction:** Enabled per rule via `include_images: true`; downloads post images to `img/`
- **Comments:** Collected per rule with configurable depth (`max_comment_depth`) and count (`max_comments`) limits
- **Embedding:** Requires `qdrant-client` and `mlx-embeddings` (installed by default via `uv sync`); Qdrant must be running at `localhost:6333`
- **Markdown frontmatter:** Posts include subreddit, author, score, timestamp, and filter metadata
