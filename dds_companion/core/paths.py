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



def _windows_documents_path() -> Path | None:
    """Resolve the real Windows Documents known folder, including redirection.

    ``Path.home() / "Documents"`` is not reliable on Windows because users may
    move Documents to another drive through Explorer. SHGetKnownFolderPath
    follows that shell redirection and therefore returns the same Documents
    location the user sees in Windows.
    """
    if not sys.platform.startswith("win"):
        return None

    try:
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        folder_id = GUID(
            0xFDD39AD0,
            0x238F,
            0x46AF,
            (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        )
        path_ptr = ctypes.c_wchar_p()
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        get_known_folder = shell32.SHGetKnownFolderPath
        get_known_folder.argtypes = [
            ctypes.POINTER(GUID),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        get_known_folder.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None

        result = get_known_folder(ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr))
        if result != 0 or not path_ptr.value:
            return None
        try:
            return Path(path_ptr.value)
        finally:
            ole32.CoTaskMemFree(ctypes.cast(path_ptr, ctypes.c_void_p))
    except Exception:
        # Path resolution must never prevent DDS from starting. The caller has
        # a conservative fallback for older/unusual Windows environments.
        return None


def default_manual_export_path(paths: RuntimePaths) -> Path:
    """Return the human-facing default directory for manually packaged exports."""
    if paths.deployment_profile == "portable":
        return paths.app_data / "exports"
    if sys.platform.startswith("win"):
        documents = _windows_documents_path() or (Path.home() / "Documents")
    else:
        documents = Path.home() / "Documents"
    return documents / "DDS Exports"

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
