from __future__ import annotations

import hashlib
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PROTECTED_TOP_LEVEL = frozenset({
    "data",
    "database",
    "config",
    "media",
    "cache",
    "backups",
    "exports",
    "dds_data",
})


class PackageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PackageInventory:
    entries: tuple[str, ...]
    uncompressed_bytes: int


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: str | Path, expected: str) -> bool:
    return sha256_file(path).lower() == expected.strip().lower()


def _safe_member_name(raw_name: str) -> str:
    name = raw_name.replace("\\", "/")
    if not name or name.startswith("/"):
        raise PackageValidationError(f"unsafe ZIP path: {raw_name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise PackageValidationError(f"unsafe ZIP path: {raw_name!r}")
    if path.parts and ":" in path.parts[0]:
        raise PackageValidationError(f"unsafe ZIP drive path: {raw_name!r}")
    return path.as_posix()


def validate_update_zip(
    path: str | Path,
    *,
    required_files: tuple[str, ...] = ("DDS.exe",),
    protected_top_level: frozenset[str] = PROTECTED_TOP_LEVEL,
) -> PackageInventory:
    archive_path = Path(path)
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise PackageValidationError(f"invalid ZIP package: {exc}") from exc

    seen: set[str] = set()
    names: list[str] = []
    total = 0
    try:
        bad_crc = archive.testzip()
        if bad_crc is not None:
            raise PackageValidationError(f"ZIP CRC failure: {bad_crc}")

        for info in archive.infolist():
            safe_name = _safe_member_name(info.filename)
            canonical = safe_name.rstrip("/").casefold()
            if canonical and canonical in seen:
                raise PackageValidationError(f"duplicate ZIP path on Windows: {safe_name}")
            if canonical:
                seen.add(canonical)

            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == stat.S_IFLNK:
                raise PackageValidationError(f"symbolic links are not allowed: {safe_name}")

            parts = PurePosixPath(safe_name).parts
            if parts and parts[0].casefold() in protected_top_level:
                raise PackageValidationError(f"package targets protected data root: {safe_name}")

            names.append(safe_name)
            if not info.is_dir():
                total += int(info.file_size)
    finally:
        archive.close()

    canonical_names = {name.rstrip("/").casefold() for name in names}
    for required in required_files:
        if required.casefold() not in canonical_names:
            raise PackageValidationError(f"required package file is missing: {required}")

    return PackageInventory(entries=tuple(names), uncompressed_bytes=total)
