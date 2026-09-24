from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[.-][0-9A-Za-z]+)*$")


class UpdateState(str, Enum):
    IDLE = "IDLE"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    STAGED = "STAGED"
    WAITING_FOR_EXIT = "WAITING_FOR_EXIT"
    BACKING_UP = "BACKING_UP"
    PROMOTING = "PROMOTING"
    VERIFYING_STARTUP = "VERIFYING_STARTUP"
    COMPLETE = "COMPLETE"
    ROLLING_BACK = "ROLLING_BACK"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    channel: str
    asset: str
    sha256: str
    size_bytes: int
    updater_protocol: int = 1
    package_format: int = 1

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseManifest":
        if not isinstance(payload, dict):
            raise ValueError("release manifest root must be an object")
        required = ("version", "channel", "asset", "sha256", "size_bytes")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError("release manifest missing: " + ", ".join(missing))
        manifest = cls(
            version=str(payload["version"]),
            channel=str(payload["channel"]),
            asset=str(payload["asset"]),
            sha256=str(payload["sha256"]).lower(),
            size_bytes=payload["size_bytes"],
            updater_protocol=payload.get("updater_protocol", 1),
            package_format=payload.get("package_format", 1),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if not _VERSION_RE.fullmatch(self.version):
            raise ValueError("version must use a supported semantic form")
        if self.channel not in {"preview", "stable"}:
            raise ValueError("channel must be preview or stable")
        if not self.asset or self.asset != self.asset.replace("\\", "/").split("/")[-1]:
            raise ValueError("asset must be a plain file name")
        if not self.asset.lower().endswith(".zip"):
            raise ValueError("asset must be a ZIP package")
        if not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes <= 0:
            raise ValueError("size_bytes must be a positive integer")
        if isinstance(self.updater_protocol, bool) or not isinstance(self.updater_protocol, int) or self.updater_protocol <= 0:
            raise ValueError("updater_protocol must be a positive integer")
        if isinstance(self.package_format, bool) or not isinstance(self.package_format, int) or self.package_format <= 0:
            raise ValueError("package_format must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
