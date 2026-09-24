from __future__ import annotations

import shutil
from pathlib import Path

SPACE_MARGIN_BYTES = 128 * 1024 * 1024


def directory_bytes(path: str | Path) -> int:
    root = Path(path)
    return sum(item.stat().st_size for item in root.rglob("*") if item.is_file())


def nearest_existing(path: str | Path) -> Path:
    current = Path(path)
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def require_free_space(path: str | Path, required_bytes: int, *, margin_bytes: int = SPACE_MARGIN_BYTES) -> None:
    probe = nearest_existing(path)
    free = shutil.disk_usage(probe).free
    needed = max(0, int(required_bytes)) + max(0, int(margin_bytes))
    if free < needed:
        raise OSError(
            f"not enough free space: need {needed} bytes including safety margin, have {free}"
        )
