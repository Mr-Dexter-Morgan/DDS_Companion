from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class CheckState:
    last_checked_at: str | None = None


class CheckStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> CheckState:
        if not self.path.exists():
            return CheckState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("last_checked_at") if isinstance(payload, dict) else None
            return CheckState(last_checked_at=str(value) if value else None)
        except Exception:
            return CheckState()

    def due(self, *, now: datetime | None = None, interval_hours: int = 24) -> bool:
        state = self.load()
        if not state.last_checked_at:
            return True
        try:
            previous = datetime.fromisoformat(state.last_checked_at)
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        current = now or datetime.now(timezone.utc)
        return current >= previous + timedelta(hours=max(1, interval_hours))

    def mark_checked(self, *, now: datetime | None = None) -> CheckState:
        current = now or datetime.now(timezone.utc)
        state = CheckState(last_checked_at=current.isoformat())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps({"last_checked_at": state.last_checked_at}, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent)
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            temp_path.unlink(missing_ok=True)
        return state
