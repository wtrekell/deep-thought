-- Stack Exchange Tool: Initial schema
-- Three tables: collected_questions (state tracking), quota_usage, key_value

CREATE TABLE IF NOT EXISTS collected_questions (
    state_key           TEXT    NOT NULL PRIMARY KEY,
    question_id         INTEGER NOT NULL,
    site                TEXT    NOT NULL,
    rule_name           TEXT    NOT NULL,
    title               TEXT    NOT NULL,
    link                TEXT    NOT NULL,
    tags                TEXT    NOT NULL DEFAULT '[]',
    score               INTEGER NOT NULL DEFAULT 0,
    answer_count        INTEGER NOT NULL DEFAULT 0,
    accepted_answer_id  INTEGER,
    output_path         TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'ok',
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cq_rule_name   ON collected_questions (rule_name);
CREATE INDEX IF NOT EXISTS idx_cq_site        ON collected_questions (site);
CREATE INDEX IF NOT EXISTS idx_cq_question_id ON collected_questions (question_id);

CREATE TABLE IF NOT EXISTS quota_usage (
    date            TEXT    NOT NULL PRIMARY KEY,
    requests_used   INTEGER NOT NULL DEFAULT 0,
    quota_remaining INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS key_value (
    key        TEXT NOT NULL PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
