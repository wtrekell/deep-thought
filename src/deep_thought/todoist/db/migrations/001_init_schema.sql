-- Migration: 001_init_schema.sql
-- Description: Initial schema for all Todoist entities
-- Preconditions: None — this is the first migration
-- Note: PRAGMA statements (journal_mode, foreign_keys) are intentionally
-- absent here. They cannot run inside a transaction, and they are already
-- applied by get_connection() before migrations execute.

-- ---------------------------------------------------------------------------
-- projects
-- Mirrors the Todoist Project model. `id` is the Todoist-issued string ID.
-- `order_index` replaces the reserved word `order`.
-- `created_at` and `updated_at` come from the API; `synced_at` tracks when
-- this row was last written by a pull operation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id                TEXT    NOT NULL PRIMARY KEY,
    name              TEXT    NOT NULL,
    description       TEXT,
    color             TEXT,
    is_archived       INTEGER NOT NULL DEFAULT 0,  -- BOOLEAN (0/1)
    is_favorite       INTEGER NOT NULL DEFAULT 0,
    is_inbox_project  INTEGER NOT NULL DEFAULT 0,
    is_shared         INTEGER NOT NULL DEFAULT 0,
    is_collapsed      INTEGER NOT NULL DEFAULT 0,
    order_index       INTEGER,
    parent_id         TEXT,
    folder_id         TEXT,
    view_style        TEXT,
    url               TEXT,
    workspace_id      TEXT,
    can_assign_tasks  INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT,                         -- ISO-8601 from API
    updated_at        TEXT,                         -- ISO-8601 from API
    synced_at         TEXT    NOT NULL              -- ISO-8601, set locally on write
);

-- ---------------------------------------------------------------------------
-- sections
-- Mirrors the Todoist Section model. Belongs to one project.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sections (
    id            TEXT    NOT NULL PRIMARY KEY,
    name          TEXT    NOT NULL,
    project_id    TEXT    NOT NULL REFERENCES projects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    order_index   INTEGER,
    is_collapsed  INTEGER NOT NULL DEFAULT 0,
    synced_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sections_project_id ON sections (project_id);

-- ---------------------------------------------------------------------------
-- tasks
-- Mirrors the Todoist Task model. Due and deadline fields are flattened from
-- their nested objects. `labels` stores a JSON array of label name strings
-- as returned by the API (denormalized for fast reads; task_labels is the
-- normalized join table for querying by label).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id                TEXT    NOT NULL PRIMARY KEY,
    content           TEXT    NOT NULL,
    description       TEXT,
    project_id        TEXT    NOT NULL REFERENCES projects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    section_id        TEXT    REFERENCES sections (id) ON DELETE SET NULL ON UPDATE CASCADE,
    parent_id         TEXT    REFERENCES tasks (id) ON DELETE SET NULL ON UPDATE CASCADE,
    order_index       INTEGER,
    priority          INTEGER NOT NULL DEFAULT 1,
    -- Due (flattened from Due object)
    due_date          TEXT,
    due_string        TEXT,
    due_is_recurring  INTEGER DEFAULT 0,             -- BOOLEAN, NULL when task has no due date
    due_lang          TEXT,
    due_timezone      TEXT,
    -- Deadline (flattened from Deadline object)
    deadline_date     TEXT,
    deadline_lang     TEXT,
    -- Duration (flattened from Duration object)
    duration_amount   INTEGER,
    duration_unit     TEXT,
    -- Collaborator references (IDs only — no local collaborator table)
    assignee_id       TEXT,
    assigner_id       TEXT,
    creator_id        TEXT,
    -- Completion state
    is_completed      INTEGER NOT NULL DEFAULT 0,
    completed_at      TEXT,
    -- Denormalized label names (JSON array, e.g. '["label-a","label-b"]')
    labels            TEXT    NOT NULL DEFAULT '[]',
    url               TEXT,
    created_at        TEXT,
    updated_at        TEXT,
    synced_at         TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_project_id  ON tasks (project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_section_id  ON tasks (section_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent_id   ON tasks (parent_id);

-- ---------------------------------------------------------------------------
-- labels
-- Mirrors the Todoist Label model.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS labels (
    id           TEXT    NOT NULL PRIMARY KEY,
    name         TEXT    NOT NULL,
    color        TEXT,
    order_index  INTEGER,
    is_favorite  INTEGER NOT NULL DEFAULT 0,
    synced_at    TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- task_labels
-- Normalized many-to-many join between tasks and labels. Enables queries
-- like "find all tasks with label X" without parsing JSON.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_labels (
    task_id   TEXT NOT NULL REFERENCES tasks (id) ON DELETE CASCADE ON UPDATE CASCADE,
    label_id  TEXT NOT NULL REFERENCES labels (id) ON DELETE CASCADE ON UPDATE CASCADE,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (task_id, label_id)
);

CREATE INDEX IF NOT EXISTS idx_task_labels_label_id ON task_labels (label_id);

-- ---------------------------------------------------------------------------
-- comments
-- Mirrors the Todoist Comment model. Both task_id and project_id are
-- nullable because the API can attach comments to either entity.
-- `attachment_json` stores the serialized Attachment object when present.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comments (
    id               TEXT NOT NULL PRIMARY KEY,
    task_id          TEXT REFERENCES tasks (id) ON DELETE CASCADE ON UPDATE CASCADE,
    project_id       TEXT REFERENCES projects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    content          TEXT NOT NULL,
    posted_at        TEXT,
    poster_id        TEXT,
    attachment_json  TEXT,   -- serialized Attachment or NULL
    synced_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_task_id    ON comments (task_id);
CREATE INDEX IF NOT EXISTS idx_comments_project_id ON comments (project_id);

-- ---------------------------------------------------------------------------
-- sync_state
-- General-purpose key/value store for sync metadata:
--   schema_version  — current migration number (integer stored as text)
--   sync_token      — last token returned by the Todoist incremental sync API
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_state (
    key        TEXT NOT NULL PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
