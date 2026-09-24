from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class UpdateLog:
    def __init__(self, path: str | Path, *, max_bytes: int = 1024 * 1024):
        self.path = Path(path)
        self.max_bytes = max(64 * 1024, int(max_bytes))

    def write(self, event: str, detail: str = "") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._rotate_if_needed()
        stamp = datetime.now(timezone.utc).isoformat()
        line = f"{stamp} [{event}] {detail}".rstrip() + "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)

    def _rotate_if_needed(self) -> None:
        try:
            if self.path.stat().st_size < self.max_bytes:
                return
        except FileNotFoundError:
            return
        previous = self.path.with_suffix(self.path.suffix + ".1")
        previous.unlink(missing_ok=True)
        self.path.replace(previous)
