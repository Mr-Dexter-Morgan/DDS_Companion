from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1


SCHEMA_SQL = r"""
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


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()
