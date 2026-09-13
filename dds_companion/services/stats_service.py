from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def directory_file_count(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += 1
        except OSError:
            continue
    return total


def sqlite_family_size(database_path: Path) -> int:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{database_path}{suffix}")
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


@dataclass(frozen=True)
class StatsSnapshot:
    messages: int
    guilds: int
    channels: int
    threads: int
    users: int
    attachments: int
    embeds: int
    imports: int
    activity_events: int
    failed_jobs_total: int
    failed_jobs_unresolved: int
    known_media: int
    cached_media_files: int
    sqlite_bytes: int
    dds_json_bytes: int
    cache_bytes: int
    media_bytes: int
    logs_bytes: int
    total_known_storage_bytes: int
    last_successful_import: str | None
    session_messages_added: int
    session_imports_added: int
    session_activity_events_added: int
    session_storage_delta_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


class StatsService:
    """Fast snapshot API with a process-session baseline for future Dashboard use."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        database_path: str | Path,
        dds_data_path: str | Path,
        *,
        cache_path: str | Path | None = None,
        media_path: str | Path | None = None,
        logs_path: str | Path | None = None,
    ):
        self.connection = connection
        self.database_path = Path(database_path)
        self.dds_data_path = Path(dds_data_path)
        self.cache_path = Path(cache_path) if cache_path else self.database_path.parent.parent / "cache"
        self.media_path = Path(media_path) if media_path else self.database_path.parent.parent / "media"
        self.logs_path = Path(logs_path) if logs_path else self.database_path.parent.parent / "logs"
        self._baseline = self._raw()

    def snapshot(self) -> StatsSnapshot:
        current = self._raw()
        return StatsSnapshot(
            **current,
            session_messages_added=current["messages"] - self._baseline["messages"],
            session_imports_added=current["imports"] - self._baseline["imports"],
            session_activity_events_added=current["activity_events"] - self._baseline["activity_events"],
            session_storage_delta_bytes=current["total_known_storage_bytes"] - self._baseline["total_known_storage_bytes"],
        )

    def _raw(self) -> dict:
        last_import_row = self.connection.execute(
            "SELECT value FROM application_state WHERE key='last_successful_import'"
        ).fetchone()
        unresolved = int(
            self.connection.execute("SELECT COUNT(*) FROM failed_jobs WHERE resolved_at IS NULL").fetchone()[0]
        )

        sqlite_bytes = sqlite_family_size(self.database_path)
        dds_size = directory_size(self.dds_data_path)
        cache_bytes = directory_size(self.cache_path)
        media_bytes = directory_size(self.media_path)
        logs_bytes = directory_size(self.logs_path)
        attachments = _count(self.connection, "attachments")

        return {
            "messages": _count(self.connection, "messages"),
            "guilds": _count(self.connection, "guilds"),
            "channels": _count(self.connection, "channels"),
            "threads": _count(self.connection, "threads"),
            "users": _count(self.connection, "users"),
            "attachments": attachments,
            "embeds": _count(self.connection, "embeds"),
            "imports": _count(self.connection, "capture_imports"),
            "activity_events": _count(self.connection, "activity_events"),
            "failed_jobs_total": _count(self.connection, "failed_jobs"),
            "failed_jobs_unresolved": unresolved,
            # Until Media stage, attachment rows are the reliable known-media unit.
            "known_media": attachments,
            "cached_media_files": directory_file_count(self.media_path),
            "sqlite_bytes": sqlite_bytes,
            "dds_json_bytes": dds_size,
            "cache_bytes": cache_bytes,
            "media_bytes": media_bytes,
            "logs_bytes": logs_bytes,
            "total_known_storage_bytes": sqlite_bytes + dds_size + cache_bytes + media_bytes + logs_bytes,
            "last_successful_import": last_import_row[0] if last_import_row else None,
        }


def collect_stats(connection: sqlite3.Connection, database_path: Path, dds_data_path: Path) -> dict:
    """Compatibility wrapper for 0.1/0.2 callers.

    The wrapper has a zero-length session by design. 0.3.0 runtime code keeps one
    StatsService instance for the full process to obtain meaningful session deltas.
    """
    return StatsService(connection, database_path, dds_data_path).snapshot().to_dict()
