from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class CheckState:
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None

    @property
    def last_checked_at(self) -> str | None:
        """Compatibility alias for 0.7.0 callers/tests."""
        return self.last_attempt_at


class CheckStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> CheckState:
        if not self.path.exists():
            return CheckState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return CheckState()
            # 0.7.0 persisted only last_checked_at. It proves an attempt happened,
            # but not that the request completed successfully.
            attempt = payload.get("last_attempt_at") or payload.get("last_checked_at")
            return CheckState(
                last_attempt_at=str(attempt) if attempt else None,
                last_success_at=(
                    str(payload.get("last_success_at"))
                    if payload.get("last_success_at")
                    else None
                ),
                last_error=(
                    str(payload.get("last_error"))
                    if payload.get("last_error")
                    else None
                ),
            )
        except Exception:
            return CheckState()

    def due(self, *, now: datetime | None = None, interval_hours: int = 24) -> bool:
        state = self.load()
        if not state.last_attempt_at:
            return True
        try:
            previous = datetime.fromisoformat(state.last_attempt_at)
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        current = now or datetime.now(timezone.utc)
        return current >= previous + timedelta(hours=max(1, interval_hours))

    def mark_attempt(self, *, now: datetime | None = None) -> CheckState:
        current = now or datetime.now(timezone.utc)
        previous = self.load()
        state = CheckState(
            last_attempt_at=current.isoformat(),
            last_success_at=previous.last_success_at,
            last_error=None,
        )
        self._write(state)
        return state

    def mark_success(self, *, now: datetime | None = None) -> CheckState:
        current = now or datetime.now(timezone.utc)
        previous = self.load()
        state = CheckState(
            last_attempt_at=previous.last_attempt_at or current.isoformat(),
            last_success_at=current.isoformat(),
            last_error=None,
        )
        self._write(state)
        return state

    def mark_failure(self, error: str, *, now: datetime | None = None) -> CheckState:
        current = now or datetime.now(timezone.utc)
        previous = self.load()
        state = CheckState(
            last_attempt_at=previous.last_attempt_at or current.isoformat(),
            last_success_at=previous.last_success_at,
            last_error=str(error),
        )
        self._write(state)
        return state

    def mark_checked(self, *, now: datetime | None = None) -> CheckState:
        """0.7.0 compatibility: a check marker means an attempt began."""
        return self.mark_attempt(now=now)

    def _write(self, state: CheckState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n"
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
