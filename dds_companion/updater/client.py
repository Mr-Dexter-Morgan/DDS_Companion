from __future__ import annotations

from dataclasses import dataclass

from .models import ReleaseManifest
from .release_source import GitHubReleaseSource, ReleaseDescriptor
from .versioning import is_newer


@dataclass(frozen=True)
class UpdateCheckResult:
    update_available: bool
    current_version: str
    descriptor: ReleaseDescriptor | None = None
    manifest: ReleaseManifest | None = None


class UpdateClient:
    def __init__(self, source: GitHubReleaseSource | None = None):
        self.source = source or GitHubReleaseSource()

    def check(self, current_version: str, *, channel: str = "preview") -> UpdateCheckResult:
        descriptor = self.source.latest(channel=channel)
        if descriptor is None or not is_newer(descriptor.version, current_version):
            return UpdateCheckResult(False, current_version)
        manifest = self.source.manifest(descriptor)
        return UpdateCheckResult(
            True,
            current_version,
            descriptor=descriptor,
            manifest=manifest,
        )
