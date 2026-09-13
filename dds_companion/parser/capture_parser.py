from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .validation import validate_capture


@dataclass(frozen=True)
class ParsedCapture:
    path: Path
    sha256: str
    size_bytes: int
    data: dict[str, Any]


def parse_capture(path: str | Path) -> ParsedCapture:
    capture_path = Path(path)
    raw = capture_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode("utf-8"))
    validate_capture(data)
    return ParsedCapture(
        path=capture_path,
        sha256=digest,
        size_bytes=len(raw),
        data=data,
    )
