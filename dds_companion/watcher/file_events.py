from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dds_companion.services.import_service import ImportResult


@dataclass(frozen=True)
class FileSignature:
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class WatcherEvent:
    kind: str
    path: Path
    result: ImportResult | None = None
    detail: str | None = None
