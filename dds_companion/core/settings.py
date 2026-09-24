from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CompanionSettings:
    """Persisted user-facing settings that already have real runtime behavior.

    Values use ``None`` for an unlimited/forever policy. 0.5.x includes the first
    real automatic media-backfill switch; every exposed control has persistent
    runtime behavior and no decorative settings are stored.
    """

    media_cache_limit_bytes: int | None = 5 * 1024**3
    media_max_file_bytes: int | None = 250 * 1024**2
    media_retention_days: int | None = 30
    media_autodownload_enabled: bool = False
    confirm_media_cache_clear: bool = True
    manual_export_path: str | None = None
    update_background_check_enabled: bool = True
    update_auto_download_enabled: bool = False
    update_auto_install_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_SETTINGS = CompanionSettings()


class SettingsStore:
    """Crash-safe JSON settings store with validation and default fallback."""

    _INT_OR_NONE = {
        "media_cache_limit_bytes": (1024**2, 1024**5),
        "media_max_file_bytes": (1024**2, 1024**4),
        "media_retention_days": (1, 36500),
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._settings = DEFAULT_SETTINGS
        self.last_load_error: str | None = None
        self.load()

    @property
    def settings(self) -> CompanionSettings:
        with self._lock:
            return self._settings

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = self._settings.to_dict()
            data["settings_path"] = str(self.path)
            data["last_load_error"] = self.last_load_error
            return data

    def load(self) -> CompanionSettings:
        with self._lock:
            self.last_load_error = None
            if not self.path.exists():
                self._settings = DEFAULT_SETTINGS
                return self._settings

            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("settings root must be a JSON object")
                self._settings = self._validated(payload)
            except Exception as exc:
                # A corrupt config must never stop Companion. Keep the file for
                # diagnostics and continue with safe defaults.
                self.last_load_error = f"{type(exc).__name__}: {exc}"
                self._settings = DEFAULT_SETTINGS
            return self._settings

    def update(self, **changes: Any) -> CompanionSettings:
        with self._lock:
            current = self._settings.to_dict()
            current.update(changes)
            validated = self._validated(current)
            self._atomic_write(validated.to_dict())
            self._settings = validated
            self.last_load_error = None
            return validated

    def reset(self) -> CompanionSettings:
        with self._lock:
            self._atomic_write(DEFAULT_SETTINGS.to_dict())
            self._settings = DEFAULT_SETTINGS
            self.last_load_error = None
            return self._settings

    def _validated(self, payload: dict[str, Any]) -> CompanionSettings:
        values = DEFAULT_SETTINGS.to_dict()
        for key in values:
            if key in payload:
                values[key] = payload[key]

        for key, (minimum, maximum) in self._INT_OR_NONE.items():
            value = values[key]
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{key} must be an integer or null")
            if not minimum <= value <= maximum:
                raise ValueError(f"{key} is outside the supported range")

        for key in (
            "media_autodownload_enabled",
            "confirm_media_cache_clear",
            "update_background_check_enabled",
            "update_auto_download_enabled",
            "update_auto_install_enabled",
        ):
            if not isinstance(values[key], bool):
                raise ValueError(f"{key} must be boolean")

        if values["update_auto_install_enabled"]:
            values["update_auto_download_enabled"] = True

        export_path = values.get("manual_export_path")
        if export_path is not None:
            if not isinstance(export_path, str):
                raise ValueError("manual_export_path must be a string or null")
            export_path = export_path.strip()
            values["manual_export_path"] = export_path or None

        return CompanionSettings(**values)

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
