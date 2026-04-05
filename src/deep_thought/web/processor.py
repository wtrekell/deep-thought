"""Crawl orchestration for the web crawl tool.

Provides mode-specific crawl runners (blog, documentation, direct) and a
top-level dispatch function that selects the appropriate runner based on
the configured mode. All runners share common page processing logic.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3  # noqa: TC003 — sqlite3.Connection is used at runtime in function signatures
import sys
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path  # noqa: TC003
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from deep_thought.progress import create_progress, track_items
from deep_thought.web.config import WebConfig  # noqa: TC001
from deep_thought.web.converter import (
    apply_boilerplate_patterns,
    convert_html_to_markdown,
    count_words,
    extract_title,
    unwrap_html_tags,
)
from deep_thought.web.crawler import CrawlerConfig, PageResult, WebCrawler
from deep_thought.web.db import queries
from deep_thought.web.filters import extract_internal_links, is_url_allowed
from deep_thought.web.image_extractor import download_images, extract_image_urls
from deep_thought.web.llms import PageSummary, strip_frontmatter, write_llms_full, write_llms_index
from deep_thought.web.models import CrawledPageLocal
from deep_thought.web.output import url_to_output_path, write_page

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class CrawlResult:
    """Summary counts for a completed crawl operation."""

    total: int
    succeeded: int
    failed: int
    skipped: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_crawler_config(config: WebConfig) -> CrawlerConfig:
    """Extract a CrawlerConfig from the top-level WebConfig.

    Args:
        config: The loaded WebConfig.

    Returns:
        A CrawlerConfig populated from config.crawl settings.
    """
    return CrawlerConfig(
        js_wait=config.crawl.js_wait,
        browser_channel=config.crawl.browser_channel,
        stealth=config.crawl.stealth,
        headless=config.crawl.headless,
        retry_attempts=config.crawl.retry_attempts,
        retry_delay=config.crawl.retry_delay,
        pagination=config.crawl.pagination,
        pagination_selector=config.crawl.pagination_selector,
        pagination_wait=config.crawl.pagination_wait,
        max_paginations=config.crawl.max_paginations,
    )


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        ISO-8601 formatted UTC timestamp string.
    """
    return datetime.now(UTC).isoformat()


def _is_article_content(word_count: int, min_words: int) -> bool:
    """Return True if a page meets the minimum word count to be treated as article content.

    Pages below the threshold are likely navigation, listing, or index pages and
    should be skipped rather than captured as content.

    Args:
        word_count: The number of words on the page.
        min_words: The configured minimum word count threshold.

    Returns:
        True if word_count >= min_words, False otherwise.
    """
    return word_count >= min_words


def _process_page(
    page_result: PageResult,
    config: WebConfig,
    output_root: Path,
    rule_name: str | None,
    dry_run: bool,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_documents",
) -> tuple[CrawledPageLocal, PageSummary | None]:
    """Convert a fetched page to markdown and build its local model.

    Converts the HTML to markdown, counts words, applies the min_article_words
    quality gate, optionally writes the output file, optionally downloads
    images, and assembles the database model and LLM summary.

    Args:
        page_result: The fetched page content from the crawler.
        config: The WebConfig controlling output and extraction settings.
        output_root: Root directory for output files.
        rule_name: The batch rule name that triggered this crawl, or None.
        dry_run: If True, skip writing files to disk.
        embedding_model: Optional MLX embedding model. When provided together
            with ``embedding_qdrant_client``, the page is embedded after writing.
        embedding_qdrant_client: Optional Qdrant client. Must be provided
            together with ``embedding_model`` for embedding to occur.
        qdrant_collection: The Qdrant collection name to write embeddings into.

    Returns:
        A tuple of (CrawledPageLocal, PageSummary | None). PageSummary is None
        when dry_run is True or when the page is skipped (below min_article_words).
    """
    now_iso = _now_iso()

    html_title = extract_title(page_result.html) or page_result.title
    page_html = page_result.html
    if config.crawl.unwrap_tags:
        page_html = unwrap_html_tags(page_html, config.crawl.unwrap_tags)
    markdown_text = convert_html_to_markdown(page_html, base_url=page_result.url)
    if config.crawl.strip_boilerplate:
        markdown_text = apply_boilerplate_patterns(markdown_text, config.crawl.strip_boilerplate)
    word_count = count_words(markdown_text)

    # Quality gate: skip pages that are too sparse to be article content
    if not _is_article_content(word_count, config.crawl.min_article_words):
        logger.debug(
            "Skipping sparse page %s (%d words < %d min_article_words)",
            page_result.url,
            word_count,
            config.crawl.min_article_words,
        )
        skip_model = CrawledPageLocal(
            url=page_result.url,
            rule_name=rule_name,
            title=html_title,
            status_code=page_result.status_code,
            word_count=word_count,
            output_path="",
            status="skipped",
            created_at=now_iso,
            updated_at=now_iso,
            synced_at=now_iso,
        )
        return skip_model, None

    if dry_run:
        output_path_str = str(
            url_to_output_path(
                page_result.url,
                output_root,
                strip_path_prefix=config.crawl.strip_path_prefix,
                strip_domain=config.crawl.strip_domain,
            )
        )
        page_model = CrawledPageLocal(
            url=page_result.url,
            rule_name=rule_name,
            title=html_title,
            status_code=page_result.status_code,
            word_count=word_count,
            output_path=output_path_str,
            status="success",
            created_at=now_iso,
            updated_at=now_iso,
            synced_at=now_iso,
        )
        return page_model, None

    written_path = write_page(
        markdown_text=markdown_text,
        url=page_result.url,
        mode=config.crawl.mode,
        title=html_title,
        word_count=word_count,
        output_root=output_root,
        strip_path_prefix=config.crawl.strip_path_prefix,
        strip_domain=config.crawl.strip_domain,
    )

    if config.crawl.extract_images:
        image_urls = extract_image_urls(page_result.html, page_result.url)
        if image_urls:
            images_output_dir = written_path.parent / "img"
            download_images(image_urls, images_output_dir)

    page_model = CrawledPageLocal(
        url=page_result.url,
        rule_name=rule_name,
        title=html_title,
        status_code=page_result.status_code,
        word_count=word_count,
        output_path=str(written_path),
        status="success",
        created_at=now_iso,
        updated_at=now_iso,
        synced_at=now_iso,
    )

    if embedding_model is not None and embedding_qdrant_client is not None:
        try:
            from deep_thought.embeddings import strip_frontmatter as _strip_frontmatter  # noqa: PLC0415
            from deep_thought.web.embeddings import write_embedding as _write_web_embedding  # noqa: PLC0415

            raw_md = written_path.read_text(encoding="utf-8")
            embed_content = f"Title: {page_model.title or ''}\n\n{_strip_frontmatter(raw_md)}"
            _write_web_embedding(
                embed_content,
                page_model,
                config.crawl.mode,
                embedding_model,
                embedding_qdrant_client,
                qdrant_collection,
            )
        except Exception as embed_err:
            logger.warning("Embedding failed for page %s: %s", page_result.url, embed_err)

    try:
        md_relative_path = written_path.relative_to(output_root).as_posix()
    except ValueError:
        md_relative_path = written_path.name

    raw_content = written_path.read_text(encoding="utf-8")
    page_content = strip_frontmatter(raw_content)

    page_summary = PageSummary(
        title=html_title,
        url=page_result.url,
        md_relative_path=md_relative_path,
        mode=config.crawl.mode,
        word_count=word_count,
        content=page_content,
    )

    return page_model, page_summary


def _record_error_page(
    url: str,
    rule_name: str | None,
    error: Exception,
    conn: sqlite3.Connection,
) -> None:
    """Record a failed page fetch in the database.

    Args:
        url: The URL that failed to fetch.
        rule_name: The batch rule name, or None.
        error: The exception that caused the failure.
        conn: An open SQLite connection.
    """
    now_iso = _now_iso()
    error_model = CrawledPageLocal(
        url=url,
        rule_name=rule_name,
        title=None,
        status_code=0,
        word_count=0,
        output_path="",
        status="error",
        created_at=now_iso,
        updated_at=now_iso,
        synced_at=now_iso,
    )
    logger.error("Failed to fetch %s: %s", url, error)
    queries.upsert_crawled_page(conn, error_model.to_dict())
    conn.commit()


def _collect_article_urls(
    crawler: WebCrawler,
    url: str,
    include_patterns: list[str],
    exclude_patterns: list[str],
    remaining_depth: int,
    visited: set[str],
    config: WebConfig | None = None,
    max_pages: int = 0,
    collected: list[str] | None = None,
) -> list[str]:
    """Recursively follow index pages to collect article URLs at the correct depth.

    At remaining_depth=0 the url itself is an article — return it.
    At remaining_depth>0 the url is an index page — fetch it, extract internal
    links, and recurse with remaining_depth-1 for each allowed child link.

    When config is provided and config.crawl.pagination is not "none", index
    pages are fetched with pagination support so that JS-rendered content
    (infinite scroll, "load more" buttons) is fully expanded before link
    extraction.

    Collection stops early once the number of article URLs gathered across all
    recursion levels reaches max_pages (when max_pages > 0). This avoids
    fetching unnecessary index pages on wide or deep sites.

    Args:
        crawler: An active WebCrawler instance.
        url: The URL to process at the current recursion level.
        include_patterns: URL include regex patterns.
        exclude_patterns: URL exclude regex patterns.
        remaining_depth: How many more levels to traverse before capturing.
        visited: Set of already-seen URLs (mutated in place to prevent loops).
        config: Optional WebConfig. When provided and pagination is enabled,
            index pages are fetched with fetch_page_with_pagination().
        max_pages: Stop collecting once this many article URLs are gathered.
            0 means no limit (collect all).
        collected: Shared mutable list tracking all collected URLs so far
            across the recursive call tree. Callers should omit this argument;
            it is managed internally.

    Returns:
        A list of article URLs at the terminal depth.
    """
    # Use a shared mutable list to track total collected count across recursion.
    if collected is None:
        collected = []

    if remaining_depth == 0:
        if max_pages <= 0 or len(collected) < max_pages:
            collected.append(url)
            return [url]
        return []

    # This URL is an index page — fetch it to extract its links.
    # Use pagination-aware fetching when a config is provided and pagination is enabled.
    use_pagination = config is not None and config.crawl.pagination != "none"
    try:
        page_result = crawler.fetch_page_with_pagination(url) if use_pagination else crawler.fetch_page(url)
    except (PlaywrightError, ConnectionError) as fetch_error:
        logger.warning("Failed to fetch index page %s: %s", url, fetch_error)
        return []

    child_links = extract_internal_links(page_result.html, url)
    article_urls: list[str] = []

    for child_url in child_links:
        if max_pages > 0 and len(collected) >= max_pages:
            break
        if child_url in visited:
            continue
        if not is_url_allowed(child_url, include_patterns, exclude_patterns):
            continue
        visited.add(child_url)
        article_urls.extend(
            _collect_article_urls(
                crawler=crawler,
                url=child_url,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                remaining_depth=remaining_depth - 1,
                visited=visited,
                config=config,
                max_pages=max_pages,
                collected=collected,
            )
        )

    return article_urls


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------


def run_blog_mode(
    crawler: WebCrawler,
    config: WebConfig,
    conn: sqlite3.Connection,
    root_url: str,
    output_root: Path,
    dry_run: bool,
    force: bool,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_documents",
) -> tuple[CrawlResult, list[PageSummary]]:
    """Traverse index pages according to index_depth, then fetch and capture articles.

    Follows config.crawl.index_depth levels of index/listing pages from root_url
    before capturing content. At index_depth=1 (default), the root URL is treated
    as a listing page and its direct links are captured as articles. At
    index_depth=2, root → category pages → article pages.

    Args:
        crawler: An active WebCrawler context manager instance.
        config: The WebConfig controlling filtering and output.
        conn: An open SQLite connection.
        root_url: The root URL to start crawling from.
        output_root: Root directory for output files.
        dry_run: If True, skip writing files to disk.
        force: If True, re-crawl URLs that were previously crawled successfully.
        embedding_model: Optional MLX embedding model. Threaded to ``_process_page``
            so each page is embedded after writing.
        embedding_qdrant_client: Optional Qdrant client. Threaded to
            ``_process_page`` for writing embeddings.
        qdrant_collection: The Qdrant collection name to write embeddings into.

    Returns:
        A tuple of (CrawlResult, list[PageSummary]) for the crawled pages.
    """
    succeeded_count = 0
    failed_count = 0
    skipped_count = 0
    summaries: list[PageSummary] = []

    visited: set[str] = {root_url}
    article_urls = _collect_article_urls(
        crawler=crawler,
        url=root_url,
        include_patterns=config.crawl.include_patterns,
        exclude_patterns=config.crawl.exclude_patterns,
        remaining_depth=config.crawl.index_depth,
        visited=visited,
        config=config,
        max_pages=config.crawl.max_pages,
    )

    # Deduplicate while preserving order (max_pages already enforced during collection)
    seen: set[str] = set()
    unique_article_urls: list[str] = []
    for article_url in article_urls:
        if article_url not in seen:
            seen.add(article_url)
            unique_article_urls.append(article_url)

    for page_url in track_items(unique_article_urls, description="Crawling pages"):
        if not force:
            existing_row = queries.get_crawled_page(conn, page_url)
            if existing_row is not None and existing_row.get("status") == "success":
                skipped_count += 1
                logger.debug("Skipping already-crawled URL: %s", page_url)
                continue

        try:
            page_result = crawler.fetch_page(page_url)

            page_model, page_summary = _process_page(
                page_result=page_result,
                config=config,
                output_root=output_root,
                rule_name=None,
                dry_run=dry_run,
                embedding_model=embedding_model,
                embedding_qdrant_client=embedding_qdrant_client,
                qdrant_collection=qdrant_collection,
            )
            queries.upsert_crawled_page(conn, page_model.to_dict())
            conn.commit()

            if page_model.status == "skipped":
                skipped_count += 1
            else:
                succeeded_count += 1
                if page_summary is not None:
                    summaries.append(page_summary)

        except (PlaywrightError, ConnectionError) as fetch_error:
            _record_error_page(page_url, None, fetch_error, conn)
            failed_count += 1
        except Exception as unexpected_error:
            logger.error("Unexpected error processing %s: %s", page_url, unexpected_error)
            _record_error_page(page_url, None, unexpected_error, conn)
            failed_count += 1

    total_count = succeeded_count + failed_count + skipped_count
    crawl_result = CrawlResult(total=total_count, succeeded=succeeded_count, failed=failed_count, skipped=skipped_count)
    return crawl_result, summaries


def _get_changelog_changed_urls(crawler: WebCrawler, changelog_url: str, root_url: str) -> set[str]:
    """Fetch the changelog page and return the set of internal URLs it links to.

    These are the pages considered to have changed since the last crawl.

    Args:
        crawler: An active WebCrawler instance.
        changelog_url: The URL of the changelog page.
        root_url: The site root URL, used for same-domain filtering.

    Returns:
        A set of absolute URLs found on the changelog page. Empty set on fetch failure.
    """
    try:
        changelog_result = crawler.fetch_page(changelog_url)
        changed_links = extract_internal_links(changelog_result.html, root_url)
        return set(changed_links)
    except (PlaywrightError, ConnectionError) as fetch_error:
        logger.warning("Failed to fetch changelog %s: %s", changelog_url, fetch_error)
        return set()


def run_documentation_mode(
    crawler: WebCrawler,
    config: WebConfig,
    conn: sqlite3.Connection,
    root_url: str,
    output_root: Path,
    dry_run: bool,
    force: bool,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_documents",
) -> tuple[CrawlResult, list[PageSummary]]:
    """Crawl a documentation site using breadth-first search.

    Follows internal links up to config.crawl.max_depth levels deep and
    stops when config.crawl.max_pages pages have been processed.

    If config.crawl.changelog_url is set and the database already contains
    crawled pages from a prior run, only pages mentioned in the changelog
    are re-fetched; all other already-crawled pages are skipped. This
    enables incremental re-crawls for docs sites with active changelogs.

    Args:
        crawler: An active WebCrawler context manager instance.
        config: The WebConfig controlling depth, page limits, and filtering.
        conn: An open SQLite connection.
        root_url: The root URL to start crawling from.
        output_root: Root directory for output files.
        dry_run: If True, skip writing files to disk.
        force: If True, re-crawl URLs that were previously crawled successfully.
        embedding_model: Optional MLX embedding model. Threaded to ``_process_page``
            so each page is embedded after writing.
        embedding_qdrant_client: Optional Qdrant client. Threaded to
            ``_process_page`` for writing embeddings.
        qdrant_collection: The Qdrant collection name to write embeddings into.

    Returns:
        A tuple of (CrawlResult, list[PageSummary]) for the crawled pages.
    """
    succeeded_count = 0
    failed_count = 0
    skipped_count = 0
    summaries: list[PageSummary] = []

    # Determine which URLs the changelog says have changed (for incremental re-crawl)
    changelog_changed_urls: set[str] = set()
    existing_pages = queries.get_all_crawled_pages(conn)
    has_prior_crawl = len(existing_pages) > 0

    if config.crawl.changelog_url is not None and has_prior_crawl and not force:
        logger.debug("Fetching changelog to determine changed pages: %s", config.crawl.changelog_url)
        changelog_changed_urls = _get_changelog_changed_urls(crawler, config.crawl.changelog_url, root_url)
        if changelog_changed_urls:
            logger.debug("Changelog lists %d changed pages for re-crawl", len(changelog_changed_urls))

    visited_urls: set[str] = set()
    url_queue: deque[tuple[str, int]] = deque()
    url_queue.append((root_url, 0))
    visited_urls.add(root_url)

    use_progress = sys.stderr.isatty()
    bfs_progress = create_progress() if use_progress else None
    bfs_task_id = None

    with bfs_progress if bfs_progress is not None else contextlib.nullcontext():
        while url_queue:
            current_url, current_depth = url_queue.popleft()

            total_processed = succeeded_count + failed_count + skipped_count
            if config.crawl.max_pages > 0 and total_processed >= config.crawl.max_pages:
                break

            if bfs_progress is not None:
                if bfs_task_id is None:
                    bfs_task_id = bfs_progress.add_task("Crawling pages", total=None)
                else:
                    bfs_progress.update(bfs_task_id, total=len(visited_urls))

            # Skip already-crawled pages unless: force, or this URL is in the changelog changes
            if not force:
                is_changelog_changed = current_url in changelog_changed_urls
                if not is_changelog_changed:
                    existing_row = queries.get_crawled_page(conn, current_url)
                    if existing_row is not None and existing_row.get("status") == "success":
                        skipped_count += 1
                        logger.debug("Skipping already-crawled URL: %s", current_url)
                        # Still enqueue children so the BFS graph stays complete
                        if current_depth < config.crawl.max_depth:
                            _enqueue_children_from_db(
                                existing_row, url_queue, visited_urls, config, root_url, current_depth
                            )
                        if bfs_progress is not None and bfs_task_id is not None:
                            bfs_progress.advance(bfs_task_id)
                        continue

            try:
                page_result = crawler.fetch_page(current_url)

                page_model, page_summary = _process_page(
                    page_result=page_result,
                    config=config,
                    output_root=output_root,
                    rule_name=None,
                    dry_run=dry_run,
                    embedding_model=embedding_model,
                    embedding_qdrant_client=embedding_qdrant_client,
                    qdrant_collection=qdrant_collection,
                )
                queries.upsert_crawled_page(conn, page_model.to_dict())
                conn.commit()

                if page_model.status == "skipped":
                    skipped_count += 1
                else:
                    succeeded_count += 1
                    if page_summary is not None:
                        summaries.append(page_summary)

                # Enqueue child links if we have not reached max depth
                if current_depth < config.crawl.max_depth:
                    child_links = extract_internal_links(page_result.html, root_url)
                    queries.update_page_child_links(conn, current_url, json.dumps(list(child_links)))
                    conn.commit()
                    for child_url in child_links:
                        if child_url not in visited_urls and is_url_allowed(
                            child_url,
                            config.crawl.include_patterns,
                            config.crawl.exclude_patterns,
                        ):
                            visited_urls.add(child_url)
                            url_queue.append((child_url, current_depth + 1))

            except (PlaywrightError, ConnectionError) as fetch_error:
                _record_error_page(current_url, None, fetch_error, conn)
                failed_count += 1
            except Exception as unexpected_error:
                logger.error("Unexpected error processing %s: %s", current_url, unexpected_error)
                _record_error_page(current_url, None, unexpected_error, conn)
                failed_count += 1

            if bfs_progress is not None and bfs_task_id is not None:
                bfs_progress.advance(bfs_task_id)

    total_count = succeeded_count + failed_count + skipped_count
    crawl_result = CrawlResult(total=total_count, succeeded=succeeded_count, failed=failed_count, skipped=skipped_count)
    return crawl_result, summaries


def _enqueue_children_from_db(
    existing_row: dict[str, object],
    url_queue: deque[tuple[str, int]],
    visited_urls: set[str],
    config: WebConfig,
    root_url: str,
    current_depth: int,
) -> None:
    """Re-enqueue child links for a cached page using stored link data.

    When a page is skipped because it was already successfully crawled, its
    previously-extracted child links (stored as JSON in the ``child_links``
    column) are parsed and filtered against the current crawl config, then
    added to the BFS queue. This preserves full BFS graph traversal without
    re-fetching the cached page.

    If ``child_links`` is absent (rows pre-dating migration 002), the page's
    children are silently skipped at DEBUG level — they will be discovered
    naturally when those URLs are reached via other paths, or on the next
    full crawl.

    Args:
        existing_row: The cached DB row for the skipped page.
        url_queue: The BFS queue to add children to.
        visited_urls: Set of already-visited URLs.
        config: The WebConfig for filter settings.
        root_url: The crawl root URL.
        current_depth: The depth of the skipped page.
    """
    child_links_json = existing_row.get("child_links")
    if not child_links_json:
        logger.debug(
            "Cached page %r has no stored child links (pre-migration row); children not traversed.",
            existing_row.get("url", "<unknown>"),
        )
        return

    try:
        child_links: list[str] = json.loads(str(child_links_json))
    except (ValueError, TypeError):
        logger.debug("Could not parse child_links for %r; skipping.", existing_row.get("url"))
        return

    for child_url in child_links:
        if child_url not in visited_urls and is_url_allowed(
            child_url,
            config.crawl.include_patterns,
            config.crawl.exclude_patterns,
        ):
            visited_urls.add(child_url)
            url_queue.append((child_url, current_depth + 1))


def run_direct_mode(
    crawler: WebCrawler,
    config: WebConfig,
    conn: sqlite3.Connection,
    url_file: Path,
    output_root: Path,
    dry_run: bool,
    force: bool,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_documents",
) -> tuple[CrawlResult, list[PageSummary]]:
    """Fetch each URL listed in a text file.

    Reads the file line by line, skipping blank lines and comment lines
    (those beginning with ``#``).

    Args:
        crawler: An active WebCrawler context manager instance.
        config: The WebConfig controlling output and extraction settings.
        conn: An open SQLite connection.
        url_file: Path to a text file with one URL per line.
        output_root: Root directory for output files.
        dry_run: If True, skip writing files to disk.
        force: If True, re-crawl URLs that were previously crawled successfully.
        embedding_model: Optional MLX embedding model. Threaded to ``_process_page``
            so each page is embedded after writing.
        embedding_qdrant_client: Optional Qdrant client. Threaded to
            ``_process_page`` for writing embeddings.
        qdrant_collection: The Qdrant collection name to write embeddings into.

    Returns:
        A tuple of (CrawlResult, list[PageSummary]) for the crawled pages.

    Raises:
        FileNotFoundError: If url_file does not exist.
    """
    if not url_file.exists():
        raise FileNotFoundError(f"URL file not found: {url_file}")

    url_lines = url_file.read_text(encoding="utf-8").splitlines()
    urls_to_crawl: list[str] = []
    for line in url_lines:
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith("#"):
            urls_to_crawl.append(stripped_line)

    succeeded_count = 0
    failed_count = 0
    skipped_count = 0
    summaries: list[PageSummary] = []

    for page_url in track_items(urls_to_crawl, description="Crawling pages"):
        if not force:
            existing_row = queries.get_crawled_page(conn, page_url)
            if existing_row is not None and existing_row.get("status") == "success":
                skipped_count += 1
                logger.debug("Skipping already-crawled URL: %s", page_url)
                continue

        try:
            page_result = crawler.fetch_page(page_url)

            page_model, page_summary = _process_page(
                page_result=page_result,
                config=config,
                output_root=output_root,
                rule_name=None,
                dry_run=dry_run,
                embedding_model=embedding_model,
                embedding_qdrant_client=embedding_qdrant_client,
                qdrant_collection=qdrant_collection,
            )
            queries.upsert_crawled_page(conn, page_model.to_dict())
            conn.commit()

            if page_model.status == "skipped":
                skipped_count += 1
            else:
                succeeded_count += 1
                if page_summary is not None:
                    summaries.append(page_summary)

        except (PlaywrightError, ConnectionError) as fetch_error:
            _record_error_page(page_url, None, fetch_error, conn)
            failed_count += 1
        except Exception as unexpected_error:
            logger.error("Unexpected error processing %s: %s", page_url, unexpected_error)
            _record_error_page(page_url, None, unexpected_error, conn)
            failed_count += 1

    total_count = succeeded_count + failed_count + skipped_count
    crawl_result = CrawlResult(total=total_count, succeeded=succeeded_count, failed=failed_count, skipped=skipped_count)
    return crawl_result, summaries


# ---------------------------------------------------------------------------
# LLMs file lookback helpers
# ---------------------------------------------------------------------------


def _build_lookback_summaries(
    conn: sqlite3.Connection,
    current_summaries: list[PageSummary],
    output_root: Path,
    lookback_days: int,
    mode: str,
) -> list[PageSummary]:
    """Merge current-run summaries with historical pages from the database.

    Queries the DB for all successful pages updated within the lookback
    window, reads their markdown content from disk, and merges with
    current-run summaries.  Current-run summaries take precedence when
    URLs overlap.

    Args:
        conn: An open SQLite connection to the web database.
        current_summaries: PageSummary objects from the current crawl run.
        output_root: Root directory where ``.md`` files are stored on disk.
        lookback_days: Number of days to look back for historical pages.
        mode: The crawl mode string (e.g. ``"blog"``).

    Returns:
        A merged, deduplicated list of PageSummary objects sorted by URL.
    """
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    since_iso = cutoff.isoformat()

    db_rows = queries.get_successful_pages_since(conn, since_iso)

    # Current-run summaries win on overlap
    merged: dict[str, PageSummary] = {s.url: s for s in current_summaries}

    for row in db_rows:
        url: str = row["url"]
        if url in merged:
            continue

        output_path_value: str = row.get("output_path", "")
        if not output_path_value:
            continue

        md_file = Path(output_path_value)
        if not md_file.is_absolute():
            md_file = output_root / md_file

        if not md_file.exists():
            logger.debug("Skipping historical page %s: file not found at %s", url, md_file)
            continue

        raw_content = md_file.read_text(encoding="utf-8")
        content = strip_frontmatter(raw_content)

        try:
            md_relative_path = md_file.relative_to(output_root).as_posix()
        except ValueError:
            md_relative_path = md_file.name

        merged[url] = PageSummary(
            title=row.get("title"),
            url=url,
            md_relative_path=md_relative_path,
            mode=mode,
            word_count=row.get("word_count", 0),
            content=content,
        )

    return sorted(merged.values(), key=lambda s: s.url)


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------


def process(
    input_url: str | None,
    input_file: Path | None,
    mode: str,
    config: WebConfig,
    conn: sqlite3.Connection,
    output_root: Path,
    dry_run: bool,
    force: bool,
    rule_name: str | None = None,
    embedding_model: Any | None = None,
    embedding_qdrant_client: Any | None = None,
    qdrant_collection: str = "deep_thought_documents",
) -> CrawlResult:
    """Top-level crawl dispatcher.

    Creates a WebCrawler, selects the appropriate mode runner, executes
    the crawl, optionally writes llms aggregate files, and returns a summary.

    Args:
        input_url: The starting URL (used for blog and documentation modes).
        input_file: Path to a URL list file (used for direct mode).
        mode: Crawl mode: 'blog', 'documentation', or 'direct'.
        config: The WebConfig controlling all crawl settings.
        conn: An open SQLite connection.
        output_root: Root directory for output files.
        dry_run: If True, skip writing files to disk.
        force: If True, re-crawl already-visited URLs.
        rule_name: Optional batch rule name that triggered this crawl.
        embedding_model: Optional MLX embedding model. Passed to the mode runner
            so each page is embedded after writing. When None, embedding is skipped.
        embedding_qdrant_client: Optional Qdrant client. Passed to the mode runner
            for writing embeddings. Must be provided with ``embedding_model``.
        qdrant_collection: The Qdrant collection name to write embeddings into.

    Returns:
        A CrawlResult with total, succeeded, failed, and skipped counts.

    Raises:
        ValueError: If mode is not one of 'blog', 'documentation', 'direct'.
        ValueError: If the required input argument for the mode is not provided.
    """
    crawler_config = _make_crawler_config(config)

    with WebCrawler(crawler_config) as crawler:
        if mode == "blog":
            if input_url is None:
                raise ValueError("blog mode requires --input URL")
            crawl_result, page_summaries = run_blog_mode(
                crawler=crawler,
                config=config,
                conn=conn,
                root_url=input_url,
                output_root=output_root,
                dry_run=dry_run,
                force=force,
                embedding_model=embedding_model,
                embedding_qdrant_client=embedding_qdrant_client,
                qdrant_collection=qdrant_collection,
            )
        elif mode == "documentation":
            if input_url is None:
                raise ValueError("documentation mode requires --input URL")
            crawl_result, page_summaries = run_documentation_mode(
                crawler=crawler,
                config=config,
                conn=conn,
                root_url=input_url,
                output_root=output_root,
                dry_run=dry_run,
                force=force,
                embedding_model=embedding_model,
                embedding_qdrant_client=embedding_qdrant_client,
                qdrant_collection=qdrant_collection,
            )
        elif mode == "direct":
            if input_file is None:
                raise ValueError("direct mode requires --input-file PATH")
            crawl_result, page_summaries = run_direct_mode(
                crawler=crawler,
                config=config,
                conn=conn,
                url_file=input_file,
                output_root=output_root,
                dry_run=dry_run,
                force=force,
                embedding_model=embedding_model,
                embedding_qdrant_client=embedding_qdrant_client,
                qdrant_collection=qdrant_collection,
            )
        else:
            raise ValueError(f"Unknown crawl mode: '{mode}'. Must be one of: blog, documentation, direct")

    if not dry_run and config.crawl.generate_llms_files:
        if config.crawl.llms_lookback_days > 0:
            llms_summaries = _build_lookback_summaries(
                conn=conn,
                current_summaries=page_summaries,
                output_root=output_root,
                lookback_days=config.crawl.llms_lookback_days,
                mode=mode,
            )
        else:
            llms_summaries = page_summaries
        if llms_summaries:
            write_llms_full(llms_summaries, output_root)
            write_llms_index(llms_summaries, output_root)

    return crawl_result
