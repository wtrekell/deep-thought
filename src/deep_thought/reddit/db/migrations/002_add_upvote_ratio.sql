-- Migration: 002_add_upvote_ratio.sql
-- Description: Add upvote_ratio column to collected_posts
-- Preconditions: Migration 001 must have been applied

ALTER TABLE collected_posts ADD COLUMN upvote_ratio REAL NOT NULL DEFAULT 0.0;
