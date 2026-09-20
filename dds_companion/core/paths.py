from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DeploymentProfile = Literal["installed", "portable", "custom"]


@dataclass(frozen=True)
class RuntimePaths:
    dds_data: Path
    app_data: Path
    database: Path
    logs: Path
    cache: Path
    media: Path
    backups: Path
    config: Path
    settings: Path
    deployment_profile: DeploymentProfile = "installed"
    application_dir: Path | None = None


def application_directory() -> Path:
    """Return the directory containing the running DDS application.

    For a frozen Windows build this is the directory containing DDS.exe. During
    source development it is the project root. Keeping this decision here gives
    Installed and Portable builds one deployment-neutral path boundary.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def default_dds_data_path() -> Path:
    """Return the default DDS plugin export root for the current platform."""
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "BetterDiscord" / "DDS_Data"
        return Path.home() / "AppData" / "Roaming" / "BetterDiscord" / "DDS_Data"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BetterDiscord" / "DDS_Data"

    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "BetterDiscord" / "DDS_Data"


def default_companion_data_path() -> Path:
    """Return the Installed-profile data root for DDS Companion."""
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local:
            return Path(local) / "DDS_Companion"
        return Path.home() / "AppData" / "Local" / "DDS_Companion"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DDS_Companion"

    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "DDS_Companion"


def portable_companion_data_path(app_dir: str | Path | None = None) -> Path:
    """Return the Portable-profile data root next to DDS.exe."""
    root = Path(app_dir).expanduser().resolve() if app_dir else application_directory()
    return root / "Data"


def resolve_data_root(
    app_data: str | Path | None = None,
    *,
    portable: bool = False,
    app_dir: str | Path | None = None,
) -> tuple[Path, DeploymentProfile]:
    """Resolve one durable DataRoot for every Companion service.

    Explicit ``app_data`` remains a supported development/diagnostic override.
    Portable mode resolves relative to the application directory. Otherwise the
    established Installed location is preserved unchanged.
    """
    if app_data is not None:
        return Path(app_data).expanduser().resolve(), "custom"
    if portable:
        return portable_companion_data_path(app_dir).resolve(), "portable"
    return default_companion_data_path().expanduser().resolve(), "installed"


def build_runtime_paths(
    dds_data: str | Path | None = None,
    app_data: str | Path | None = None,
    *,
    portable: bool = False,
    app_dir: str | Path | None = None,
) -> RuntimePaths:
    dds_root = Path(dds_data).expanduser().resolve() if dds_data else default_dds_data_path().expanduser().resolve()
    app_root, profile = resolve_data_root(app_data, portable=portable, app_dir=app_dir)
    resolved_app_dir = Path(app_dir).expanduser().resolve() if app_dir else application_directory()

    return RuntimePaths(
        dds_data=dds_root,
        app_data=app_root,
        database=app_root / "database" / "dds.sqlite3",
        logs=app_root / "logs",
        cache=app_root / "cache",
        media=app_root / "media",
        backups=app_root / "backups",
        config=app_root / "config",
        settings=app_root / "config" / "settings.json",
        deployment_profile=profile,
        application_dir=resolved_app_dir,
    )


def ensure_runtime_dirs(paths: RuntimePaths) -> None:
    for directory in (
        paths.app_data,
        paths.database.parent,
        paths.logs,
        paths.cache,
        paths.media,
        paths.backups,
        paths.config,
    ):
        directory.mkdir(parents=True, exist_ok=True)
