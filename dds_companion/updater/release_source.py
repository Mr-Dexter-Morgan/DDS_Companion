from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .models import ReleaseManifest
from .versioning import version_key


class ReleaseSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseDescriptor:
    version: str
    prerelease: bool
    manifest_url: str
    release_url: str
    notes: str
    published_at: str | None
    asset_urls: dict[str, str]


class GitHubReleaseSource:
    def __init__(
        self,
        repository: str = "Mr-Dexter-Morgan/DDS_Companion",
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 2,
        retry_delay_seconds: float = 0.25,
        opener: Callable | None = None,
    ):
        self.repository = repository
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_attempts = max(1, min(3, int(max_attempts)))
        self.retry_delay_seconds = max(0.0, min(2.0, float(retry_delay_seconds)))
        self._opener = opener or urllib.request.urlopen

    def _json(self, url: str):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "DDS-Companion-Updater/1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except ValueError as exc:
                # Malformed JSON is not a transient transport problem.
                raise ReleaseSourceError(f"release metadata response is invalid: {exc}") from exc
            except (OSError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)
        raise ReleaseSourceError(
            f"release metadata request failed after {self.max_attempts} attempt(s): {last_error}"
        ) from last_error

    def latest(self, *, channel: str = "preview") -> ReleaseDescriptor | None:
        if channel not in {"preview", "stable"}:
            raise ValueError("channel must be preview or stable")
        releases = self._json(
            f"https://api.github.com/repos/{self.repository}/releases?per_page=20"
        )
        if not isinstance(releases, list):
            raise ReleaseSourceError("GitHub releases response is not a list")

        candidates: list[ReleaseDescriptor] = []
        for release in releases:
            if not isinstance(release, dict) or release.get("draft"):
                continue
            prerelease = bool(release.get("prerelease"))
            if channel == "stable" and prerelease:
                continue
            tag = str(release.get("tag_name") or "")
            try:
                key = version_key(tag)
            except ValueError:
                continue
            version = f"{key.major}.{key.minor}.{key.patch}"
            expected_manifest = f"DDS-{version}-update.json"
            asset_urls: dict[str, str] = {}
            for asset in release.get("assets") or []:
                if not isinstance(asset, dict):
                    continue
                name = str(asset.get("name") or "")
                url = str(asset.get("browser_download_url") or "")
                if name and url:
                    asset_urls[name] = url
            manifest_url = asset_urls.get(expected_manifest, "")
            if not manifest_url:
                continue
            candidates.append(ReleaseDescriptor(
                version=version,
                prerelease=prerelease,
                manifest_url=manifest_url,
                release_url=str(release.get("html_url") or ""),
                notes=str(release.get("body") or ""),
                published_at=release.get("published_at"),
                asset_urls=asset_urls,
            ))

        if not candidates:
            return None
        return max(candidates, key=lambda item: version_key(item.version))

    def manifest(self, descriptor: ReleaseDescriptor) -> ReleaseManifest:
        payload = self._json(descriptor.manifest_url)
        manifest = ReleaseManifest.from_dict(payload)
        if manifest.version != descriptor.version:
            raise ReleaseSourceError(
                f"manifest version {manifest.version} does not match release {descriptor.version}"
            )
        return manifest
