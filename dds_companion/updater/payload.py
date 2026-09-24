from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .integrity import PROTECTED_TOP_LEVEL, sha256_file

INSTALL_MANIFEST_NAME = "DDS.install.json"
INSTALL_SCHEMA = "dds-install-manifest-v1"


@dataclass(frozen=True)
class PayloadFile:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class InstallManifest:
    version: str
    files: tuple[PayloadFile, ...]
    schema: str = INSTALL_SCHEMA

    @classmethod
    def load(cls, path: str | Path) -> "InstallManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema") != INSTALL_SCHEMA:
            raise ValueError("unsupported install manifest schema")
        version = str(payload.get("version") or "")
        records: list[PayloadFile] = []
        seen: set[str] = set()
        for item in payload.get("files") or []:
            rel = _validate_payload_path(str(item.get("path") or ""))
            key = rel.casefold()
            if key in seen:
                raise ValueError(f"duplicate payload path: {rel}")
            seen.add(key)
            digest = str(item.get("sha256") or "").lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"invalid payload SHA-256: {rel}")
            size = item.get("size_bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError(f"invalid payload size: {rel}")
            records.append(PayloadFile(rel, digest, size))
        if not version or not records:
            raise ValueError("install manifest is incomplete")
        return cls(version=version, files=tuple(records))

    def verify(self, payload_root: str | Path) -> None:
        root = Path(payload_root)
        for record in self.files:
            path = root.joinpath(*PurePosixPath(record.path).parts)
            if not path.is_file():
                raise ValueError(f"payload file is missing: {record.path}")
            if path.stat().st_size != record.size_bytes:
                raise ValueError(f"payload size mismatch: {record.path}")
            if sha256_file(path) != record.sha256:
                raise ValueError(f"payload SHA-256 mismatch: {record.path}")


def _validate_payload_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe payload path: {value!r}")
    if not path.parts or ":" in path.parts[0]:
        raise ValueError(f"unsafe payload path: {value!r}")
    if path.parts[0].casefold() in PROTECTED_TOP_LEVEL:
        raise ValueError(f"payload targets protected root: {value}")
    return path.as_posix()


def create_install_manifest(payload_root: str | Path, version: str) -> InstallManifest:
    root = Path(payload_root)
    files: list[PayloadFile] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: str(p).casefold()):
        if path.name == INSTALL_MANIFEST_NAME:
            continue
        rel = _validate_payload_path(path.relative_to(root).as_posix())
        files.append(PayloadFile(rel, sha256_file(path), path.stat().st_size))
    if not files:
        raise ValueError("payload is empty")
    return InstallManifest(version=version, files=tuple(files))


def write_install_manifest(payload_root: str | Path, manifest: InstallManifest) -> Path:
    root = Path(payload_root)
    target = root / INSTALL_MANIFEST_NAME
    body = {
        "schema": manifest.schema,
        "version": manifest.version,
        "files": [
            {"path": record.path, "sha256": record.sha256, "size_bytes": record.size_bytes}
            for record in manifest.files
        ],
    }
    encoded = json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".DDS.install.", suffix=".tmp", dir=str(root))
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
