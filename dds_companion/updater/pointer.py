from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

CURRENT_POINTER = "current.json"
PREVIOUS_POINTER = "previous.json"
PENDING_UPDATE = "pending_update.json"
POINTER_SCHEMA = "dds-version-pointer-v1"
PENDING_SCHEMA = "dds-pending-update-v1"


@dataclass(frozen=True)
class VersionPointer:
    version: str
    relative_path: str
    schema: str = POINTER_SCHEMA

    def validate(self) -> None:
        path = PurePosixPath(self.relative_path.replace("\\", "/"))
        if self.schema != POINTER_SCHEMA:
            raise ValueError("unsupported pointer schema")
        if not self.version or path.is_absolute() or ".." in path.parts:
            raise ValueError("invalid version pointer")
        if tuple(path.parts) != ("versions", self.version):
            raise ValueError("version pointer must target versions/<version>")

    def to_dict(self) -> dict[str, str]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "VersionPointer":
        pointer = cls(
            version=str(payload.get("version") or ""),
            relative_path=str(payload.get("relative_path") or ""),
            schema=str(payload.get("schema") or ""),
        )
        pointer.validate()
        return pointer


@dataclass(frozen=True)
class PendingUpdate:
    previous: VersionPointer
    candidate: VersionPointer
    ack_path: str
    resume_state_path: str | None
    launch_args: tuple[str, ...] = ()
    timeout_seconds: int = 30
    journal_path: str | None = None
    log_path: str | None = None
    schema: str = PENDING_SCHEMA

    def to_dict(self) -> dict:
        if self.schema != PENDING_SCHEMA:
            raise ValueError("unsupported pending-update schema")
        self.previous.validate()
        self.candidate.validate()
        return {
            "schema": self.schema,
            "previous": self.previous.to_dict(),
            "candidate": self.candidate.to_dict(),
            "ack_path": self.ack_path,
            "resume_state_path": self.resume_state_path,
            "launch_args": list(self.launch_args),
            "timeout_seconds": self.timeout_seconds,
            "journal_path": self.journal_path,
            "log_path": self.log_path,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "PendingUpdate":
        if payload.get("schema") != PENDING_SCHEMA:
            raise ValueError("unsupported pending-update schema")
        timeout = int(payload.get("timeout_seconds") or 30)
        if not 5 <= timeout <= 300:
            raise ValueError("invalid pending-update timeout")
        return cls(
            previous=VersionPointer.from_dict(payload["previous"]),
            candidate=VersionPointer.from_dict(payload["candidate"]),
            ack_path=str(payload.get("ack_path") or ""),
            resume_state_path=payload.get("resume_state_path"),
            launch_args=tuple(str(item) for item in (payload.get("launch_args") or [])),
            timeout_seconds=timeout,
            journal_path=payload.get("journal_path"),
            log_path=payload.get("log_path"),
        )


def read_json(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def read_pointer(path: str | Path) -> VersionPointer:
    return VersionPointer.from_dict(read_json(path))


def atomic_write_json(path: str | Path, payload: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)
    return target


def write_pointer(path: str | Path, pointer: VersionPointer) -> Path:
    return atomic_write_json(path, pointer.to_dict())


def write_pending(path: str | Path, pending: PendingUpdate) -> Path:
    return atomic_write_json(path, pending.to_dict())
