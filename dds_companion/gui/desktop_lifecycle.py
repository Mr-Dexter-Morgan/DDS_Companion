from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "DDS"


def build_autostart_command(application_dir: str | Path, *, portable: bool) -> str:
    """Build the Windows Run entry against the stable DDS launcher."""
    launcher = Path(application_dir) / "DDS.exe"
    args = [str(launcher), "--autostart"]
    if portable:
        args.append("--portable")
    return subprocess.list2cmdline(args)


def startup_presentation(*, is_autostart: bool, minimize_on_autostart: bool) -> str:
    if is_autostart and minimize_on_autostart:
        return "minimized"
    return "normal"


def should_hide_on_close(
    *,
    close_to_tray: bool,
    tray_available: bool,
    explicit_exit: bool,
    update_install_launched: bool,
) -> bool:
    return bool(
        close_to_tray
        and tray_available
        and not explicit_exit
        and not update_install_launched
    )


class WindowsAutostartManager:
    """Own only the current-user Windows Run entry for the stable DDS.exe."""

    def __init__(self, application_dir: str | Path | None, *, portable: bool):
        self.application_dir = Path(application_dir) if application_dir else None
        self.portable = bool(portable)

    @property
    def supported(self) -> bool:
        return sys.platform == "win32" and self.application_dir is not None

    @property
    def command(self) -> str:
        if self.application_dir is None:
            raise RuntimeError("DDS application directory is unavailable")
        return build_autostart_command(self.application_dir, portable=self.portable)

    def is_enabled(self) -> bool:
        if not self.supported:
            return False
        try:
            winreg = self._winreg()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_RUN_KEY) as key:
                value, value_type = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return value_type == winreg.REG_SZ and str(value) == self.command
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        if not self.supported:
            raise RuntimeError("Autostart is available only in the packaged Windows application")
        winreg = self._winreg()
        if enabled:
            launcher = self.application_dir / "DDS.exe"  # type: ignore[operator]
            if not launcher.is_file():
                raise RuntimeError(f"Stable DDS launcher was not found: {launcher}")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_RUN_KEY) as key:
                winreg.SetValueEx(key, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, self.command)
            return

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                AUTOSTART_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
        except FileNotFoundError:
            pass

    @staticmethod
    def _winreg():
        import winreg

        return winreg
