from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 4

BASE_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    username TEXT,
    global_name TEXT,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guilds (
    id TEXT PRIMARY KEY,
    name TEXT,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT,
    type INTEGER,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY(guild_id) REFERENCES guilds(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    parent_channel_id TEXT NOT NULL,
    name TEXT,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY(guild_id) REFERENCES guilds(id) ON DELETE CASCADE,
    FOREIGN KEY(parent_channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT,
    global_name TEXT,
    display_name TEXT,
    bot INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    source_channel_id TEXT NOT NULL,
    parent_channel_id TEXT NOT NULL,
    thread_id TEXT,
    author_id TEXT,
    type INTEGER,
    timestamp TEXT,
    edited_timestamp TEXT,
    content TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0,
    tts INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_capture_revision INTEGER,
    FOREIGN KEY(guild_id) REFERENCES guilds(id) ON DELETE CASCADE,
    FOREIGN KEY(parent_channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE SET NULL,
    FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_guild ON messages(guild_id);
CREATE INDEX IF NOT EXISTS idx_messages_parent_channel ON messages(parent_channel_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_author ON messages(author_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

CREATE TABLE IF NOT EXISTS attachments (
    message_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    attachment_id TEXT,
    filename TEXT,
    title TEXT,
    description TEXT,
    content_type TEXT,
    size INTEGER,
    url TEXT,
    proxy_url TEXT,
    width INTEGER,
    height INTEGER,
    ephemeral INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(message_id, position),
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attachments_id ON attachments(attachment_id);
CREATE INDEX IF NOT EXISTS idx_attachments_content_type ON attachments(content_type);

CREATE TABLE IF NOT EXISTS embeds (
    message_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    type TEXT,
    url TEXT,
    title TEXT,
    description TEXT,
    timestamp TEXT,
    color INTEGER,
    provider_json TEXT,
    author_json TEXT,
    thumbnail_json TEXT,
    image_json TEXT,
    fields_json TEXT,
    footer_json TEXT,
    PRIMARY KEY(message_id, position),
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS message_references (
    message_id TEXT PRIMARY KEY,
    referenced_message_id TEXT,
    referenced_channel_id TEXT,
    referenced_guild_id TEXT,
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS capture_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    captured_at TEXT,
    imported_at TEXT NOT NULL,
    dds_version TEXT,
    schema_version INTEGER,
    capture_revision INTEGER,
    guild_id TEXT,
    parent_channel_id TEXT,
    thread_id TEXT,
    message_count INTEGER NOT NULL DEFAULT 0,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    detail TEXT,
    UNIQUE(capture_path, sha256)
);

CREATE INDEX IF NOT EXISTS idx_capture_imports_path ON capture_imports(capture_path);
CREATE INDEX IF NOT EXISTS idx_capture_imports_imported_at ON capture_imports(imported_at);

CREATE TABLE IF NOT EXISTS failed_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_kind TEXT NOT NULL,
    target TEXT,
    error_type TEXT,
    error_message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS application_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
"""

V2_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    level TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT,
    capture_path TEXT,
    guild_id TEXT,
    parent_channel_id TEXT,
    thread_id TEXT,
    messages_new INTEGER NOT NULL DEFAULT 0,
    messages_refreshed INTEGER NOT NULL DEFAULT 0,
    attachments_registered INTEGER NOT NULL DEFAULT 0,
    embeds_registered INTEGER NOT NULL DEFAULT 0,
    storage_delta_bytes INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_activity_events_occurred_at
    ON activity_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_events_subsystem
    ON activity_events(subsystem, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_events_type
    ON activity_events(event_type, occurred_at DESC);

CREATE TABLE IF NOT EXISTS subsystem_health (
    subsystem TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    summary TEXT,
    last_ok_at TEXT,
    last_error_at TEXT,
    updated_at TEXT NOT NULL,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_subsystem_health_state ON subsystem_health(state);
"""


V3_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS media_objects (
    media_key TEXT PRIMARY KEY,
    attachment_id TEXT,
    filename TEXT,
    content_type TEXT,
    expected_size INTEGER,
    current_url TEXT,
    proxy_url TEXT,
    url_observed_at TEXT,
    state TEXT NOT NULL DEFAULT 'KNOWN',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_attempt_at TEXT,
    local_relpath TEXT,
    local_size INTEGER,
    sha256 TEXT,
    cached_at TEXT,
    last_access_at TEXT,
    last_http_status INTEGER,
    last_error TEXT,
    failure_class TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_media_objects_attachment_id
    ON media_objects(attachment_id) WHERE attachment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_media_objects_state_retry
    ON media_objects(state, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_media_objects_updated_at
    ON media_objects(updated_at);

CREATE TABLE IF NOT EXISTS media_refs (
    message_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    media_key TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY(message_id, position),
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE,
    FOREIGN KEY(media_key) REFERENCES media_objects(media_key) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_media_refs_media_key ON media_refs(media_key);
"""


V4_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS archive_export_rules (
    scope_kind TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('INCLUDE', 'EXCLUDE')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(scope_kind, scope_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_export_rules_mode
    ON archive_export_rules(mode);
"""


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply additive migrations in place.

    Migrations are additive. 0.5.4 adds future-export selection rules without
    rewriting archive/message/media tables, so older verified databases upgrade in place.
    """
    connection.executescript(BASE_SCHEMA_SQL)
    connection.executescript(V2_SCHEMA_SQL)
    connection.executescript(V3_SCHEMA_SQL)
    connection.executescript(V4_SCHEMA_SQL)
    connection.execute(
        "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()
