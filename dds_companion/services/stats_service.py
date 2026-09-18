from __future__ import annotations

import sqlite3
import time
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
    physical_media_files: int
    media_queued: int
    media_downloading: int
    media_retryable_failed: int
    media_permanent_failed: int
    media_stale_url: int
    media_too_large: int
    media_skipped: int
    media_evicted: int
    media_ignored: int
    sqlite_bytes: int
    dds_json_bytes: int
    cache_bytes: int
    media_bytes: int
    logs_bytes: int
    backups_bytes: int
    config_bytes: int
    other_bytes: int
    total_known_storage_bytes: int
    last_successful_import: str | None
    session_messages_added: int
    session_imports_added: int
    session_activity_events_added: int
    session_storage_delta_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


class StatsService:
    """Fast snapshot API with a cached storage scan.

    Database counters are cheap and stay live. Recursive filesystem size walks are
    cached for a short interval so a large archive cannot monopolize the watcher
    thread every time the GUI refreshes. A manual/meaningful forced snapshot asks
    for a fresh storage scan.
    """

    STORAGE_SCAN_INTERVAL_SECONDS = 10.0

    def __init__(
        self,
        connection: sqlite3.Connection,
        database_path: str | Path,
        dds_data_path: str | Path,
        *,
        cache_path: str | Path | None = None,
        media_path: str | Path | None = None,
        logs_path: str | Path | None = None,
        backups_path: str | Path | None = None,
        config_path: str | Path | None = None,
    ):
        self.connection = connection
        self.database_path = Path(database_path)
        self.dds_data_path = Path(dds_data_path)
        root = self.database_path.parent.parent
        self.cache_path = Path(cache_path) if cache_path else root / "cache"
        self.media_path = Path(media_path) if media_path else root / "media"
        self.logs_path = Path(logs_path) if logs_path else root / "logs"
        self.backups_path = Path(backups_path) if backups_path else root / "backups"
        self.config_path = Path(config_path) if config_path else root / "config"
        self._storage_cache: dict[str, int] = {}
        self._last_storage_scan_at = 0.0
        self._baseline = self._raw(force_storage=True)

    def snapshot(self, *, force_storage: bool = False) -> StatsSnapshot:
        current = self._raw(force_storage=force_storage)
        return StatsSnapshot(
            **current,
            session_messages_added=current["messages"] - self._baseline["messages"],
            session_imports_added=current["imports"] - self._baseline["imports"],
            session_activity_events_added=current["activity_events"] - self._baseline["activity_events"],
            session_storage_delta_bytes=current["total_known_storage_bytes"] - self._baseline["total_known_storage_bytes"],
        )

    def _storage_metrics(self, *, force: bool = False) -> dict[str, int]:
        now = time.monotonic()
        if (
            not force
            and self._storage_cache
            and now - self._last_storage_scan_at < self.STORAGE_SCAN_INTERVAL_SECONDS
        ):
            return dict(self._storage_cache)

        sqlite_bytes = sqlite_family_size(self.database_path)
        dds_size = directory_size(self.dds_data_path)
        cache_bytes = directory_size(self.cache_path)
        media_bytes = directory_size(self.media_path)
        logs_bytes = directory_size(self.logs_path)
        backups_bytes = directory_size(self.backups_path)
        config_bytes = directory_size(self.config_path)
        physical_media_files = directory_file_count(self.media_path)
        other_bytes = cache_bytes + backups_bytes + config_bytes
        total = sqlite_bytes + dds_size + media_bytes + logs_bytes + other_bytes

        self._storage_cache = {
            "sqlite_bytes": sqlite_bytes,
            "dds_json_bytes": dds_size,
            "cache_bytes": cache_bytes,
            "media_bytes": media_bytes,
            "logs_bytes": logs_bytes,
            "backups_bytes": backups_bytes,
            "config_bytes": config_bytes,
            "other_bytes": other_bytes,
            "physical_media_files": physical_media_files,
            "total_known_storage_bytes": total,
        }
        self._last_storage_scan_at = now
        return dict(self._storage_cache)

    def _raw(self, *, force_storage: bool = False) -> dict:
        last_import_row = self.connection.execute(
            "SELECT value FROM application_state WHERE key='last_successful_import'"
        ).fetchone()
        unresolved = int(
            self.connection.execute("SELECT COUNT(*) FROM failed_jobs WHERE resolved_at IS NULL").fetchone()[0]
        )

        attachments = _count(self.connection, "attachments")
        storage = self._storage_metrics(force=force_storage)
        state_rows = self.connection.execute(
            "SELECT state, COUNT(*) FROM media_objects GROUP BY state"
        ).fetchall()
        media_states = {str(row[0]): int(row[1]) for row in state_rows}
        known_media = int(
            self.connection.execute("SELECT COUNT(DISTINCT media_key) FROM media_refs").fetchone()[0]
        )

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
            "known_media": known_media,
            "cached_media_files": media_states.get("CACHED", 0),
            "media_queued": media_states.get("QUEUED", 0),
            "media_downloading": media_states.get("DOWNLOADING", 0),
            "media_retryable_failed": media_states.get("FAILED_RETRYABLE", 0),
            "media_permanent_failed": media_states.get("FAILED_PERMANENT", 0),
            "media_stale_url": media_states.get("STALE_URL", 0),
            "media_too_large": media_states.get("TOO_LARGE", 0),
            "media_skipped": media_states.get("SKIPPED", 0),
            "media_evicted": media_states.get("EVICTED", 0),
            "media_ignored": media_states.get("IGNORED", 0),
            "last_successful_import": last_import_row[0] if last_import_row else None,
            **storage,
        }


def collect_stats(connection: sqlite3.Connection, database_path: Path, dds_data_path: Path) -> dict:
    """Compatibility wrapper for 0.1/0.2 callers.

    The wrapper has a zero-length session by design. GUI runtime keeps one
    StatsService instance for the full process to obtain meaningful session deltas.
    """
    return StatsService(connection, database_path, dds_data_path).snapshot().to_dict()
