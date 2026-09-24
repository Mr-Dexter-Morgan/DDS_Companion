from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from dds_companion.core.fs_scan import iter_directories, iter_regular_files
from dds_companion.core.settings import CompanionSettings
from dds_companion.services.media_registry_service import MediaRegistryService
from dds_companion.storage.database import connect_database


@dataclass(frozen=True)
class MediaCacheMaintenanceResult:
    files_removed: int = 0
    bytes_removed: int = 0
    oversized_removed: int = 0
    expired_removed: int = 0
    limit_evicted: int = 0
    registry_rows_reset: int = 0
    errors: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class MediaCacheService:
    """Bounded maintenance for Companion's media *binary* cache only.

    SQLite, DDS JSON and message/attachment metadata are never deletion targets.
    When a database path is supplied, removed registered cache files are marked
    ``EVICTED`` in the media registry so metadata stays truthful without creating
    an automatic download -> eviction -> redownload loop.
    """

    def __init__(self, media_root: str | Path, database_path: str | Path | None = None):
        self.media_root = Path(media_root)
        self.database_path = Path(database_path) if database_path else None

    def clear(self) -> MediaCacheMaintenanceResult:
        self.media_root.mkdir(parents=True, exist_ok=True)
        removed = 0
        bytes_removed = 0
        errors = 0
        relpaths: list[str] = []
        for path in self._files():
            try:
                size = path.stat().st_size
                relpaths.append(path.relative_to(self.media_root).as_posix())
                path.unlink()
                removed += 1
                bytes_removed += size
            except OSError:
                errors += 1
        self._prune_empty_dirs()
        reset, sync_errors = self._sync_registry_removed(relpaths, eviction_reason="manual_clear")
        return MediaCacheMaintenanceResult(
            files_removed=removed,
            bytes_removed=bytes_removed,
            registry_rows_reset=reset,
            errors=errors + sync_errors,
        )

    def enforce(self, settings: CompanionSettings, *, now: float | None = None) -> MediaCacheMaintenanceResult:
        self.media_root.mkdir(parents=True, exist_ok=True)
        current_time = time.time() if now is None else float(now)
        removed = bytes_removed = oversized = expired = evicted = errors = 0
        removed_relpaths: list[str] = []

        access_times = self._registry_access_times()
        survivors: list[tuple[Path, int, float]] = []
        retention_seconds = None if settings.media_retention_days is None else settings.media_retention_days * 86400

        for path in self._files():
            try:
                stat = path.stat()
                size = int(stat.st_size)
                mtime = float(stat.st_mtime)
                relpath = path.relative_to(self.media_root).as_posix()
            except OSError:
                errors += 1
                continue

            last_access = access_times.get(relpath, mtime)
            reason: str | None = None
            if settings.media_max_file_bytes is not None and size > settings.media_max_file_bytes:
                reason = "oversized"
            elif retention_seconds is not None and current_time - last_access > retention_seconds:
                reason = "expired"

            if reason:
                try:
                    path.unlink()
                    removed_relpaths.append(relpath)
                    removed += 1
                    bytes_removed += size
                    oversized += int(reason == "oversized")
                    expired += int(reason == "expired")
                except OSError:
                    errors += 1
                    survivors.append((path, size, last_access))
            else:
                survivors.append((path, size, last_access))

        limit = settings.media_cache_limit_bytes
        if limit is not None:
            total = sum(item[1] for item in survivors)
            # Least-recently-accessed first. Stable path tie-break makes behavior
            # deterministic; orphan/manual files fall back to filesystem mtime.
            survivors.sort(key=lambda item: (item[2], str(item[0]).lower()))
            for path, size, _last_access in survivors:
                if total <= limit:
                    break
                try:
                    relpath = path.relative_to(self.media_root).as_posix()
                    path.unlink()
                    removed_relpaths.append(relpath)
                    removed += 1
                    bytes_removed += size
                    evicted += 1
                    total -= size
                except OSError:
                    errors += 1

        self._prune_empty_dirs()
        reset, sync_errors = self._sync_registry_removed(removed_relpaths, eviction_reason="policy")
        return MediaCacheMaintenanceResult(
            files_removed=removed,
            bytes_removed=bytes_removed,
            oversized_removed=oversized,
            expired_removed=expired,
            limit_evicted=evicted,
            registry_rows_reset=reset,
            errors=errors + sync_errors,
        )

    def _files(self) -> list[Path]:
        if not self.media_root.exists():
            return []
        result: list[Path] = []
        staging = (self.media_root / ".staging").resolve()
        for path in iter_regular_files(self.media_root):
            try:
                if not path.is_file():
                    continue
                try:
                    path.resolve().relative_to(staging)
                    # Active .part files belong to the downloader, not the cache
                    # maintenance surface. The downloader cleans its own staging.
                    continue
                except ValueError:
                    pass
                result.append(path)
            except OSError:
                continue
        return result

    def _registry_access_times(self) -> dict[str, float]:
        if self.database_path is None or not self.database_path.exists():
            return {}
        connection: sqlite3.Connection | None = None
        try:
            connection = connect_database(self.database_path)
            rows = connection.execute(
                "SELECT local_relpath, last_access_at, cached_at FROM media_objects WHERE state='CACHED'"
            ).fetchall()
            result: dict[str, float] = {}
            for row in rows:
                relpath = row["local_relpath"]
                if not relpath:
                    continue
                raw = row["last_access_at"] or row["cached_at"]
                if not raw:
                    continue
                try:
                    result[str(relpath).replace("\\", "/")] = datetime.fromisoformat(
                        str(raw).replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    continue
            return result
        except sqlite3.Error:
            return {}
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _sync_registry_removed(
        self, relpaths: list[str], *, eviction_reason: str
    ) -> tuple[int, int]:
        if not relpaths or self.database_path is None or not self.database_path.exists():
            return 0, 0
        connection: sqlite3.Connection | None = None
        try:
            connection = connect_database(self.database_path)
            changed = MediaRegistryService(connection).reset_removed_cache_paths(
                relpaths, eviction_reason=eviction_reason
            )
            return changed, 0
        except (sqlite3.Error, OSError):
            return 0, 1
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _prune_empty_dirs(self) -> None:
        if not self.media_root.exists():
            return
        directories = [p for p in iter_directories(self.media_root) if p.name != ".staging"]
        directories.sort(key=lambda p: len(p.parts), reverse=True)
        for path in directories:
            try:
                path.rmdir()
            except OSError:
                pass
