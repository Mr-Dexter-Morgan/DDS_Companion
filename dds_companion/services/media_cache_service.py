from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dds_companion.core.settings import CompanionSettings


@dataclass(frozen=True)
class MediaCacheMaintenanceResult:
    files_removed: int = 0
    bytes_removed: int = 0
    oversized_removed: int = 0
    expired_removed: int = 0
    limit_evicted: int = 0
    errors: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class MediaCacheService:
    """Bounded maintenance for Companion's media *binary* cache only.

    The service never touches SQLite, DDS JSON, or archive metadata. Until the
    Media Backfill stage records explicit last-access timestamps, retention uses
    file mtime as the conservative age signal.
    """

    def __init__(self, media_root: str | Path):
        self.media_root = Path(media_root)

    def clear(self) -> MediaCacheMaintenanceResult:
        self.media_root.mkdir(parents=True, exist_ok=True)
        removed = 0
        bytes_removed = 0
        errors = 0
        for path in self._files():
            try:
                size = path.stat().st_size
                path.unlink()
                removed += 1
                bytes_removed += size
            except OSError:
                errors += 1
        self._prune_empty_dirs()
        return MediaCacheMaintenanceResult(
            files_removed=removed,
            bytes_removed=bytes_removed,
            errors=errors,
        )

    def enforce(self, settings: CompanionSettings, *, now: float | None = None) -> MediaCacheMaintenanceResult:
        self.media_root.mkdir(parents=True, exist_ok=True)
        current_time = time.time() if now is None else float(now)
        removed = bytes_removed = oversized = expired = evicted = errors = 0

        survivors: list[tuple[Path, int, float]] = []
        retention_seconds = None if settings.media_retention_days is None else settings.media_retention_days * 86400

        for path in self._files():
            try:
                stat = path.stat()
                size = int(stat.st_size)
                mtime = float(stat.st_mtime)
            except OSError:
                errors += 1
                continue

            reason: str | None = None
            if settings.media_max_file_bytes is not None and size > settings.media_max_file_bytes:
                reason = "oversized"
            elif retention_seconds is not None and current_time - mtime > retention_seconds:
                reason = "expired"

            if reason:
                try:
                    path.unlink()
                    removed += 1
                    bytes_removed += size
                    oversized += int(reason == "oversized")
                    expired += int(reason == "expired")
                except OSError:
                    errors += 1
                    survivors.append((path, size, mtime))
            else:
                survivors.append((path, size, mtime))

        limit = settings.media_cache_limit_bytes
        if limit is not None:
            total = sum(item[1] for item in survivors)
            # Oldest mtime first. Stable path tie-break keeps maintenance
            # deterministic across runs.
            survivors.sort(key=lambda item: (item[2], str(item[0]).lower()))
            for path, size, _mtime in survivors:
                if total <= limit:
                    break
                try:
                    path.unlink()
                    removed += 1
                    bytes_removed += size
                    evicted += 1
                    total -= size
                except OSError:
                    errors += 1

        self._prune_empty_dirs()
        return MediaCacheMaintenanceResult(
            files_removed=removed,
            bytes_removed=bytes_removed,
            oversized_removed=oversized,
            expired_removed=expired,
            limit_evicted=evicted,
            errors=errors,
        )

    def _files(self) -> list[Path]:
        if not self.media_root.exists():
            return []
        result: list[Path] = []
        for path in self.media_root.rglob("*"):
            try:
                if path.is_file():
                    result.append(path)
            except OSError:
                continue
        return result

    def _prune_empty_dirs(self) -> None:
        if not self.media_root.exists():
            return
        directories = [p for p in self.media_root.rglob("*") if p.is_dir()]
        directories.sort(key=lambda p: len(p.parts), reverse=True)
        for path in directories:
            try:
                path.rmdir()
            except OSError:
                pass
