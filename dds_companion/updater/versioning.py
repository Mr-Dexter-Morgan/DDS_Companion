from __future__ import annotations

import re
from dataclasses import dataclass

_VERSION_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:(?:[.-])(?P<suffix>[0-9A-Za-z][0-9A-Za-z.-]*))?$"
)


@dataclass(frozen=True, order=True)
class VersionKey:
    major: int
    minor: int
    patch: int
    stability: int
    suffix: str


def version_key(value: str) -> VersionKey:
    match = _VERSION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"unsupported version: {value}")
    suffix = match.group("suffix") or ""
    return VersionKey(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        1 if not suffix else 0,
        suffix.casefold(),
    )


def is_newer(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)
