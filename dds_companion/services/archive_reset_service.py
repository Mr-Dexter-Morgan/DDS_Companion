from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from dds_companion.core.paths import RuntimePaths, ensure_runtime_dirs
from dds_companion.storage.database import connect_database


RESET_MARKER_NAME = "archive_reset_boundary.json"


@dataclass(frozen=True)
class ArchiveResetResult:
    database_files_removed: int = 0
    media_files_removed: int = 0
    media_bytes_removed: int = 0
    marker_written: bool = False
    database_recreated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def reset_marker_path(paths: RuntimePaths) -> Path:
    return paths.config / RESET_MARKER_NAME


def load_capture_not_before_ns(paths: RuntimePaths) -> int | None:
    """Return the archive-reset capture boundary, if one exists.

    The marker lives outside SQLite so resetting the archive cannot erase the
    decision to ignore capture files that already existed before the reset.
    A capture becomes eligible again as soon as the Plugin rewrites it and its
    filesystem mtime moves beyond this boundary.
    """
    marker = reset_marker_path(paths)
    if not marker.is_file():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        value = payload.get("capture_not_before_ns")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _latest_existing_capture_mtime_ns(dds_data: Path) -> int:
    latest = 0
    guilds = dds_data / "guilds"
    if not guilds.is_dir():
        return latest
    for path in guilds.glob("**/capture.json"):
        try:
            latest = max(latest, int(path.stat().st_mtime_ns))
        except OSError:
            continue
    return latest


def _clear_tree_files(root: Path) -> tuple[int, int]:
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return 0, 0
    files = 0
    bytes_removed = 0
    for path in sorted((p for p in root.rglob("*") if p.is_file()), reverse=True):
        try:
            bytes_removed += int(path.stat().st_size)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        files += 1
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    root.mkdir(parents=True, exist_ok=True)
    return files, bytes_removed


def reset_local_archive(paths: RuntimePaths) -> ArchiveResetResult:
    """Delete the local archive + media cache, preserve settings, recreate DB.

    Caller must first stop the archive runtime so no SQLite/watcher/media worker
    still owns the files. DDS_Data is intentionally preserved. A reset boundary
    prevents those pre-existing capture files from being immediately re-imported;
    only files created/rewritten after reset are eligible again.
    """
    ensure_runtime_dirs(paths)

    boundary = max(time.time_ns(), _latest_existing_capture_mtime_ns(paths.dds_data))
    marker = reset_marker_path(paths)
    _atomic_write_json(
        marker,
        {
            "capture_not_before_ns": boundary,
            "created_at_unix_ns": time.time_ns(),
            "reason": "user_full_local_archive_reset",
        },
    )

    removed_db = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(paths.database) + suffix)
        if candidate.exists():
            candidate.unlink()
            removed_db += 1

    media_files, media_bytes = _clear_tree_files(paths.media)

    # Recreate a clean DB immediately so the UI/restarted runtime never sees an
    # ambiguous half-reset state.
    connection = connect_database(paths.database)
    connection.close()

    return ArchiveResetResult(
        database_files_removed=removed_db,
        media_files_removed=media_files,
        media_bytes_removed=media_bytes,
        marker_written=marker.is_file(),
        database_recreated=paths.database.is_file(),
    )
