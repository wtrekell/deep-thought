# Product Brief — Reddit Tool

## Name and Purpose

**Reddit Tool** — collects posts and comments from subreddits via the Reddit API (PRAW). Rule-based configuration supports multiple subreddits with independent filtering. Incremental updates detect new comments on previously collected posts.

## Operations

1. **CLI Command** — `reddit` (entry point)
2. **Collect** — Fetch posts and comments matching rule filters; re-fetches known posts to detect new comments (default operation)

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **PRAW** (`praw>=7.7.1`) for Reddit API access via OAuth 2.0 client credentials. [PRAW documentation](https://praw.readthedocs.io/en/stable/).
3. SQLite for local state tracking (WAL mode, foreign keys enabled).
4. Reddit API credentials: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` stored in `.env` or system environment.
5. A changelog is maintained in `files/tools/reddit/CHANGELOG.md`.

## Data Storage

### State Database

Located at `data/reddit/reddit.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `collected_posts` — columns: `state_key TEXT PRIMARY KEY`, `post_id TEXT`, `subreddit TEXT`, `rule_name TEXT`, `title TEXT`, `author TEXT`, `score INT`, `comment_count INT`, `url TEXT`, `is_video INT`, `flair TEXT`, `word_count INT`, `output_path TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`, `synced_at TEXT`
- **Composite state key:** `{post_id}:{subreddit}:{rule_name}` — allows the same post to be collected by multiple rules independently
- On incremental update, stored `comment_count` is compared to live count to detect new activity
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

## Data Models

### CollectedPostLocal

| Field           | Type          | Description                                                |
| --------------- | ------------- | ---------------------------------------------------------- |
| `state_key`     | `str`         | Composite primary key: `{post_id}:{subreddit}:{rule_name}` |
| `post_id`       | `str`         | Reddit post ID                                             |
| `subreddit`     | `str`         | Subreddit name                                             |
| `rule_name`     | `str`         | Name of the rule that collected this post                  |
| `title`         | `str`         | Post title                                                 |
| `author`        | `str`         | Reddit username of the post author                         |
| `score`         | `int`         | Post upvote score at time of collection                    |
| `comment_count` | `int`         | Number of comments at time of collection                   |
| `url`           | `str`         | Full Reddit URL to the post                                |
| `is_video`      | `int`         | 1 if the post is a video, 0 otherwise                      |
| `flair`         | `str \| None` | Post flair text                                            |
| `word_count`    | `int`         | Word count of generated markdown (post body + comments)    |
| `output_path`   | `str`         | Path to the generated markdown file                        |
| `status`        | `str`         | Processing status (e.g., `ok`, `error`)                    |
| `created_at`    | `str`         | ISO 8601 timestamp of first collection                     |
| `updated_at`    | `str`         | ISO 8601 timestamp of last update                          |
| `synced_at`     | `str`         | ISO 8601 timestamp of last API sync                        |

Methods: `from_sdk()` for API object conversion, `to_dict()` for database insertion.

## Command List

Running `reddit` with no arguments shows help. Collect is the default operation — no subcommand required.

| Subcommand      | Description                                     |
| --------------- | ----------------------------------------------- |
| `reddit config` | Validate and display current YAML configuration |
| `reddit init`   | Create config file and directory structure      |

| Flag                 | Description                                                               |
| -------------------- | ------------------------------------------------------------------------- |
| `--config PATH`      | YAML configuration file (default: `src/config/reddit-configuration.yaml`) |
| `--rule NAME`        | Run only the named rule (default: all rules)                              |
| `--output PATH`      | Output directory override                                                 |
| `--dry-run`          | Preview without processing                                                |
| `--verbose`, `-v`    | Detailed logging                                                          |
| `--force`            | Clear state and reprocess all                                             |
| `--save-config PATH` | Generate example config and exit                                          |
| `--version`          | Show version and exit                                                     |

## File & Output Map

```
files/tools/reddit/
├── 260322-requirements.md       # This document
├── api-model.md                 # PRAW SDK model reference (Submission, Comment, Subreddit)
└── CHANGELOG.md                 # Release history

src/deep_thought/reddit/
├── __init__.py
├── cli.py                       # CLI entry point
├── config.py                    # YAML config loader and rule validation
├── models.py                    # Local dataclasses for collection state
├── processor.py                 # Rule engine, comment fetching, output orchestration
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations (composite key aware)
│   └── migrations/
│       └── 001_init_schema.sql
├── filters.py                   # Score, age, keyword, flair filtering
├── output.py                    # Markdown + YAML frontmatter generation
├── image_extractor.py           # Image download: extracts URLs from markdown, saves to img/
├── embeddings.py                # Qdrant write: embeds collected posts (optional)
├── llms.py                      # .llms.txt / .llms-full.txt generation
├── utils.py                     # Shared helpers: slugify_title (delegates to text_utils), get_author_name
└── client.py                    # PRAW API client wrapper

data/reddit/
├── reddit.db                    # SQLite state database
├── snapshots/                   # Raw JSON blobs per collection run
│   └── YYYY-MM-DDTHHMMSS.json
└── export/                      # Generated markdown files

src/config/
├── reddit-configuration.yaml   # Tool configuration and rules (default)
└── reddit/                     # Alternative rule configs for one-off runs
```

## Configuration

Configuration is stored in `src/config/reddit-configuration.yaml`. All values below are required unless marked optional.

```yaml
# API credentials
client_id_env: "REDDIT_CLIENT_ID"
client_secret_env: "REDDIT_CLIENT_SECRET"
user_agent_env: "REDDIT_USER_AGENT"
# Note: PRAW manages Reddit API rate limiting internally (60 requests/minute)

# Collection
max_posts_per_run: 500 # Global cap across all rules per invocation

# Output
output_dir: "data/reddit/export/"
generate_llms_files: false # Set true to generate .llms.txt / .llms-full.txt per rule

rules:
  - name: "python_top_week"
    subreddit: "python"
    sort: "top" # 'new', 'hot', 'top', 'rising'
    time_filter: "week" # For 'top': 'hour', 'day', 'week', 'month', 'year', 'all'
    limit: 25
    min_score: 50
    min_comments: 5
    max_age_days: 7
    include_keywords: # Post must match at least one (glob wildcards supported)
      - "python 3*"
      - "asyncio"
    exclude_keywords:
      - "hiring"
    include_flair: [] # Only collect posts with these flair values (empty = all)
    exclude_flair:
      - "Meme"
    search_comments: false # Also match keywords in comment bodies
    max_comment_depth: 3
    max_comments: 200 # Max comments to collect per post (default: 200)
    include_images: true # Include image URLs in output; download linked images to img/
```

### Filter Reference

| Filter              | Description                                                    |
| ------------------- | -------------------------------------------------------------- |
| `sort`              | `new`, `hot`, `top`, `rising`                                  |
| `time_filter`       | For `top` sort: `hour`, `day`, `week`, `month`, `year`, `all`  |
| `min_score`         | Minimum post upvote score                                      |
| `min_comments`      | Minimum comment count                                          |
| `max_age_days`      | Maximum post age in days                                       |
| `include_keywords`  | Post must match at least one keyword (glob `*` supported)      |
| `exclude_keywords`  | Post must not match any of these                               |
| `include_flair`     | Only collect posts with these flair values (empty = all)       |
| `exclude_flair`     | Skip posts with these flair values                             |
| `search_comments`   | Extend keyword matching to comment bodies                      |
| `max_comment_depth` | Recursion depth for comment trees (default: 3)                 |
| `max_comments`      | Max comments to collect per post (default: 200)                |
| `include_images`    | Download direct image links (jpg/png/gif/webp) to `img/` subdirectory and rewrite markdown references to local paths. Failures log a warning and leave the original URL. |

## Data Format

### Markdown Output

```
data/reddit/export/{rule_name}/
├── {YYMMDD}-{post_id}_{title_slug}.md
└── llm/
    ├── {YYMMDD}-{post_id}_{title_slug}.llms.txt
    └── {YYMMDD}-{post_id}_{title_slug}.llms-full.txt
```

### Frontmatter Schema

```markdown
---
tool: reddit
state_key: abc123:python:python_top_week
post_id: abc123
subreddit: python
rule: python_top_week
title: "Python 3.13 performance improvements"
author: u/username
score: 1842
num_comments: 234
url: https://www.reddit.com/r/python/comments/abc123/
is_video: false
flair: "Discussion"
word_count: 3842
processed_date: 2026-03-18T10:00:00Z
---
```

### Content Structure

```markdown
# Post Title

**Score:** 1,842 | **Comments:** 234 | **Posted:** 2026-03-15 by u/username

Post body / selftext here.

---

## Comments

### u/commenter_one (↑ 145)

Top-level comment text here.

> **u/nested_reply (↑ 32)**
>
> Reply text here.
```

### llms-full.txt (generate_llms_files only)

One file per rule in the export root. Each post is separated by a delimiter block:

```
# {Post Title}

post_id: abc123
subreddit: python
rule: python_top_week
score: 1842
comments: 234
collected: 2026-03-18T10:00:00Z

{full markdown content, frontmatter stripped}

---

# {Next Post}
...
```

### llms.txt (generate_llms_files only)

Index file per rule in the export root, following the llmstxt.org convention:

```
# Post Index — python_top_week

> Collected by reddit on 2026-03-18. {N} posts.

## Posts

- [{title_slug}.md]({rule_name}/{YYMMDD}-{post_id}_{title_slug}.md): r/{subreddit}, score {score}, {word_count} words
- [{title_slug}.md]({rule_name}/{YYMMDD}-{post_id}_{title_slug}.md): r/{subreddit}, score {score}, {word_count} words
```

## Error Handling

- `PRAW API errors` (rate limits, auth, 403) — caught per-post; the post is skipped, the failure is logged with the state key, and collection continues with remaining posts.
- `Comment tree recursion errors` — caught per-post during comment traversal; partial comment data is written and a warning is logged.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Missing config file raises `FileNotFoundError`. Invalid config content raises `ValueError`. Missing required env vars raise `OSError`.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- Use in-memory SQLite for all database tests.
- Mock targets: `PRAW` — use `MagicMock` for Reddit, Subreddit, Submission, and Comment objects.
- Test fixtures: mock Reddit post and comment objects covering self posts, link posts, and nested comment trees.
- Organize tests in classes by feature area (collection, filtering, composite key logic, incremental update, output).
- Mark full collection cycle tests with `@pytest.mark.slow`.
- Mark network-dependent tests with `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Write docstrings on every test method.
- Test directory: `tests/reddit/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/reddit/fixtures/`
