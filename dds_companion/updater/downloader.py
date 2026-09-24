from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .cancel import CancelCheck, UpdateCancelled, raise_if_cancelled
from .integrity import verify_sha256
from .models import ReleaseManifest


class DownloadError(RuntimeError):
    pass


class PackageDownloader:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_attempts: int = 2,
        retry_delay_seconds: float = 0.25,
        opener: Callable | None = None,
    ):
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_attempts = max(1, min(3, int(max_attempts)))
        self.retry_delay_seconds = max(0.0, min(2.0, float(retry_delay_seconds)))
        self._opener = opener or urllib.request.urlopen

    def download(
        self,
        url: str,
        destination: str | Path,
        manifest: ReleaseManifest,
        *,
        cancel_check: CancelCheck | None = None,
    ) -> Path:
        manifest.validate()
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        partial.unlink(missing_ok=True)

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            raise_if_cancelled(cancel_check)
            partial.unlink(missing_ok=True)
            try:
                return self._download_once(
                    url,
                    target,
                    partial,
                    manifest,
                    cancel_check=cancel_check,
                )
            except UpdateCancelled:
                partial.unlink(missing_ok=True)
                raise
            except (OSError, urllib.error.URLError, DownloadError) as exc:
                partial.unlink(missing_ok=True)
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                raise_if_cancelled(cancel_check)
                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)

        if isinstance(last_error, DownloadError):
            raise last_error
        raise DownloadError(f"download failed after {self.max_attempts} attempt(s): {last_error}") from last_error

    def _download_once(
        self,
        url: str,
        target: Path,
        partial: Path,
        manifest: ReleaseManifest,
        *,
        cancel_check: CancelCheck | None,
    ) -> Path:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "DDS-Companion-Updater/1"},
        )
        written = 0
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                with partial.open("wb") as handle:
                    while True:
                        raise_if_cancelled(cancel_check)
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > manifest.size_bytes:
                            raise DownloadError("download exceeded manifest size")
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
            raise_if_cancelled(cancel_check)
            if written != manifest.size_bytes:
                raise DownloadError("download size does not match manifest")
            if not verify_sha256(partial, manifest.sha256):
                raise DownloadError("download SHA-256 does not match manifest")
            os.replace(partial, target)
            return target
        except UpdateCancelled:
            raise
        except (OSError, urllib.error.URLError, DownloadError):
            raise
