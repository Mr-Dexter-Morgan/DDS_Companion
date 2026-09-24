from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import UpdateState


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_ALLOWED_TRANSITIONS: dict[UpdateState, frozenset[UpdateState]] = {
    UpdateState.IDLE: frozenset({UpdateState.DOWNLOADING, UpdateState.VERIFYING}),
    UpdateState.DOWNLOADING: frozenset({UpdateState.VERIFYING, UpdateState.FAILED, UpdateState.CANCELLED}),
    UpdateState.VERIFYING: frozenset({UpdateState.STAGED, UpdateState.FAILED, UpdateState.CANCELLED}),
    UpdateState.STAGED: frozenset({UpdateState.WAITING_FOR_EXIT, UpdateState.FAILED}),
    UpdateState.WAITING_FOR_EXIT: frozenset({UpdateState.BACKING_UP, UpdateState.FAILED}),
    UpdateState.BACKING_UP: frozenset({UpdateState.PROMOTING, UpdateState.ROLLING_BACK, UpdateState.FAILED}),
    UpdateState.PROMOTING: frozenset({UpdateState.VERIFYING_STARTUP, UpdateState.ROLLING_BACK, UpdateState.FAILED}),
    UpdateState.VERIFYING_STARTUP: frozenset({UpdateState.COMPLETE, UpdateState.ROLLING_BACK, UpdateState.FAILED}),
    UpdateState.ROLLING_BACK: frozenset({UpdateState.FAILED}),
    UpdateState.COMPLETE: frozenset({UpdateState.IDLE}),
    UpdateState.FAILED: frozenset({UpdateState.IDLE, UpdateState.DOWNLOADING, UpdateState.VERIFYING}),
    UpdateState.CANCELLED: frozenset({UpdateState.IDLE, UpdateState.DOWNLOADING, UpdateState.VERIFYING}),
}


@dataclass(frozen=True)
class JournalEntry:
    state: UpdateState
    current_version: str
    target_version: str | None = None
    detail: str | None = None
    updated_at: str = ""

    def to_dict(self) -> dict[str, str | None]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


class JournalStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> JournalEntry | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return JournalEntry(
            state=UpdateState(payload["state"]),
            current_version=str(payload["current_version"]),
            target_version=payload.get("target_version"),
            detail=payload.get("detail"),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def write(self, entry: JournalEntry) -> JournalEntry:
        stamped = JournalEntry(
            state=entry.state,
            current_version=entry.current_version,
            target_version=entry.target_version,
            detail=entry.detail,
            updated_at=entry.updated_at or utc_now(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(stamped.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            temp_path.unlink(missing_ok=True)
        return stamped


class UpdateStateMachine:
    def __init__(self, store: JournalStore, *, current_version: str):
        self.store = store
        self.current_version = current_version

    def transition(
        self,
        current: UpdateState,
        new: UpdateState,
        *,
        target_version: str | None = None,
        detail: str | None = None,
    ) -> JournalEntry:
        if new not in _ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"invalid updater transition: {current.value} -> {new.value}")
        return self.store.write(JournalEntry(
            state=new,
            current_version=self.current_version,
            target_version=target_version,
            detail=detail,
        ))
