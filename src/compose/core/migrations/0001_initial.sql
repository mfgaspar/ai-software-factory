-- compose schema v1. Timestamps are ISO-8601 UTC text, except lock heartbeats (epoch seconds).

CREATE TABLE repos (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    path            TEXT NOT NULL UNIQUE,
    origin_url      TEXT,
    default_branch  TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE features (
    id              TEXT PRIMARY KEY,
    repo_id         TEXT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    number          INTEGER NOT NULL,
    slug            TEXT NOT NULL,
    name            TEXT NOT NULL,          -- "003-user-auth"; also the branch name
    branch          TEXT NOT NULL,
    worktree_path   TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (repo_id, name)
);

CREATE TABLE runs (
    id                TEXT PRIMARY KEY,
    repo_id           TEXT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    feature_id        TEXT REFERENCES features(id) ON DELETE SET NULL,
    workflow_id       TEXT NOT NULL,
    workflow_version  TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN
                        ('created','running','completed','paused','failed','aborted')),
    parent_run_id     TEXT REFERENCES runs(id) ON DELETE CASCADE,
    parent_exec_id    TEXT,
    current_step_id   TEXT,
    inputs_json       TEXT NOT NULL DEFAULT '{}',
    outputs_json      TEXT,
    abort_requested   INTEGER NOT NULL DEFAULT 0,
    error             TEXT,
    created_at        TEXT NOT NULL,
    started_at        TEXT,
    ended_at          TEXT
);
CREATE INDEX runs_repo_idx ON runs (repo_id, created_at);
CREATE INDEX runs_feature_idx ON runs (feature_id, created_at);
CREATE INDEX runs_status_idx ON runs (status);

CREATE TABLE step_execs (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id             TEXT NOT NULL,
    step_type           TEXT NOT NULL,
    parent_exec_id      TEXT REFERENCES step_execs(id) ON DELETE CASCADE,
    iteration           INTEGER,
    attempt             INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL CHECK (status IN
                          ('pending','running','completed','failed','skipped','paused','aborted')),
    started_at          TEXT,
    ended_at            TEXT,
    duration_ms         INTEGER,
    engine              TEXT,
    model               TEXT,
    session_id          TEXT,
    turns               INTEGER,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0,
    files_changed       INTEGER NOT NULL DEFAULT 0,
    lines_added         INTEGER NOT NULL DEFAULT 0,
    lines_removed       INTEGER NOT NULL DEFAULT 0,
    output_json         TEXT,
    error               TEXT
);
CREATE INDEX step_execs_run_idx ON step_execs (run_id, started_at);

CREATE TABLE hook_execs (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_exec_id        TEXT REFERENCES step_execs(id) ON DELETE CASCADE, -- NULL for run hooks
    event               TEXT NOT NULL,       -- e.g. before_plan, after_step, before_run
    hook_index          INTEGER NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('command','prompt','run','builtin')),
    name                TEXT NOT NULL,
    optional            INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL CHECK (status IN
                          ('pending','running','completed','failed','skipped','paused','aborted')),
    started_at          TEXT,
    ended_at            TEXT,
    duration_ms         INTEGER,
    engine              TEXT,
    model               TEXT,
    session_id          TEXT,
    turns               INTEGER,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd            REAL NOT NULL DEFAULT 0,
    files_changed       INTEGER NOT NULL DEFAULT 0,
    lines_added         INTEGER NOT NULL DEFAULT 0,
    lines_removed       INTEGER NOT NULL DEFAULT 0,
    error               TEXT
);
CREATE INDEX hook_execs_step_idx ON hook_execs (step_exec_id);
CREATE INDEX hook_execs_run_idx ON hook_execs (run_id);

CREATE TABLE actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_exec_id    TEXT REFERENCES step_execs(id) ON DELETE CASCADE,
    hook_exec_id    TEXT REFERENCES hook_execs(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,        -- order within the run
    kind            TEXT NOT NULL,           -- message | tool_call | tool_result | usage_update
    tool_name       TEXT,
    input_summary   TEXT,
    result_summary  TEXT,
    is_error        INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER,
    ts              TEXT NOT NULL,
    UNIQUE (run_id, seq)
);
CREATE INDEX actions_step_idx ON actions (step_exec_id, seq);

CREATE TABLE file_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_exec_id    TEXT NOT NULL REFERENCES step_execs(id) ON DELETE CASCADE,
    hook_exec_id    TEXT REFERENCES hook_execs(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    old_path        TEXT,
    status          TEXT NOT NULL CHECK (status IN ('A','M','D','R','C','T')),
    added           INTEGER,                 -- NULL for binary files
    removed         INTEGER
);
CREATE INDEX file_changes_step_idx ON file_changes (step_exec_id);

CREATE TABLE locks (
    key             TEXT PRIMARY KEY,        -- e.g. "feature:<feature_id>"
    owner           TEXT NOT NULL,           -- random token of the holder
    pid             INTEGER NOT NULL,
    hostname        TEXT NOT NULL,
    run_id          TEXT,
    acquired_at     REAL NOT NULL,
    heartbeat_at    REAL NOT NULL
);
