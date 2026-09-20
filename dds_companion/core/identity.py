from __future__ import annotations

import ctypes
import sys
from pathlib import Path

PRODUCT_NAME = "DDS — Discord Data Snatcher"
APPLICATION_NAME = "DDS"
APPLICATION_DISPLAY_NAME = "DDS — Discord Data Snatcher"
APP_USER_MODEL_ID = "DDS.DiscordDataSnatcher.Companion"
EXECUTABLE_NAME = "DDS.exe"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resource_path(relative: str | Path) -> Path:
    """Resolve a bundled asset both in source and PyInstaller builds."""
    relative = Path(relative)
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / relative
    return project_root() / relative


def set_windows_app_user_model_id() -> bool:
    """Set stable Windows taskbar identity before QApplication is created."""
    if not sys.platform.startswith("win"):
        return False
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        return True
    except Exception:
        # Identity failure must never prevent DDS from starting.
        return False
