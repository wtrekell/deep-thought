-- Migration 002: add child_links column to crawled_pages
--
-- Stores the JSON-encoded list of internal links extracted from each page
-- at crawl time. Used by the BFS crawler to re-enqueue children on cache
-- hits without re-fetching the page HTML.
--
-- NULL for rows created before this migration; those pages will be
-- re-fetched when next encountered at depth < max_depth.

ALTER TABLE crawled_pages ADD COLUMN child_links TEXT;
