from __future__ import annotations

import unittest
from pathlib import Path

from dds_companion.gui.desktop_lifecycle import (
    build_autostart_command,
    should_hide_on_close,
    startup_presentation,
)


class DesktopLifecycle080Tests(unittest.TestCase):
    def test_autostart_targets_stable_launcher(self):
        root = Path(r"C:\Program Files\DDS")
        command = build_autostart_command(root, portable=False)
        self.assertIn(str(root / "DDS.exe"), command)
        self.assertIn("--autostart", command)
        self.assertNotIn("DDSApp.exe", command)

    def test_portable_autostart_keeps_portable_profile(self):
        root = Path(r"D:\Portable Apps\DDS")
        command = build_autostart_command(root, portable=True)
        self.assertIn("--autostart", command)
        self.assertIn("--portable", command)

    def test_close_to_tray_only_when_tray_can_restore_window(self):
        self.assertTrue(
            should_hide_on_close(
                close_to_tray=True,
                tray_available=True,
                explicit_exit=False,
                update_install_launched=False,
            )
        )
        self.assertFalse(
            should_hide_on_close(
                close_to_tray=True,
                tray_available=False,
                explicit_exit=False,
                update_install_launched=False,
            )
        )
        self.assertFalse(
            should_hide_on_close(
                close_to_tray=True,
                tray_available=True,
                explicit_exit=True,
                update_install_launched=False,
            )
        )
        self.assertFalse(
            should_hide_on_close(
                close_to_tray=True,
                tray_available=True,
                explicit_exit=False,
                update_install_launched=True,
            )
        )

    def test_start_minimized_is_scoped_to_autostart(self):
        self.assertEqual(startup_presentation(is_autostart=False, minimize_on_autostart=True), "normal")
        self.assertEqual(startup_presentation(is_autostart=True, minimize_on_autostart=False), "normal")
        self.assertEqual(startup_presentation(is_autostart=True, minimize_on_autostart=True), "minimized")


if __name__ == "__main__":
    unittest.main()
