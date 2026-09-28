from __future__ import annotations

import unittest
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from dds_companion.gui.desktop_lifecycle import (
    build_autostart_command,
    should_hide_on_close,
    startup_presentation,
)


class DesktopLifecycle080Tests(unittest.TestCase):
    def test_tray_exit_quits_event_loop_after_close_to_tray(self):
        # Use a separate Qt process, without constructing runtime/user-data services.
        script = textwrap.dedent('''
            from types import SimpleNamespace
            from unittest.mock import Mock
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
            from dds_companion.gui.window import MainWindow

            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)

            class TestWindow(MainWindow):
                showEvent = QMainWindow.showEvent
                resizeEvent = QMainWindow.resizeEvent

                def __init__(self):
                    QMainWindow.__init__(self)
                    self.settings_store = SimpleNamespace(settings=SimpleNamespace(
                        desktop_close_to_tray_enabled=True,
                        update_auto_install_enabled=False,
                    ))
                    self._tray_available = True
                    self._tray_notice_shown = True
                    self._tray_icon = Mock()
                    self._explicit_exit = False
                    self._update_install_launched = False
                    self._closing = False
                    self.update_controller = SimpleNamespace(prepared=None)
                    self.status_text = QLabel()
                    self.runtime = Mock()
                    self.runtime_thread = Mock()
                    self.runtime_thread.is_alive.return_value = True

            window = TestWindow()
            window.show()
            observed = []
            app.aboutToQuit.connect(lambda: observed.append('quit'))

            def close_to_tray():
                assert not window.close()
                assert not window.isVisible()
                assert not window._closing
                window.runtime.stop.assert_not_called()
                QTimer.singleShot(0, window._exit_from_tray)

            QTimer.singleShot(0, close_to_tray)
            QTimer.singleShot(3000, lambda: app.exit(99))
            result = app.exec()
            assert result == 0, f'explicit exit failed to quit: {result}'
            assert observed == ['quit']
            assert window._explicit_exit and window._closing
            window.runtime.stop.assert_called_once_with()
            window.runtime_thread.join.assert_called_once_with(timeout=1.8)
            window._tray_icon.hide.assert_called_once_with()
        ''')
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_start_in_tray_is_scoped_to_autostart_and_tray_availability(self):
        self.assertEqual(
            startup_presentation(
                is_autostart=False,
                start_in_tray=True,
                tray_available=True,
            ),
            "normal",
        )
        self.assertEqual(
            startup_presentation(
                is_autostart=True,
                start_in_tray=False,
                tray_available=True,
            ),
            "normal",
        )
        self.assertEqual(
            startup_presentation(
                is_autostart=True,
                start_in_tray=True,
                tray_available=False,
            ),
            "normal",
        )
        self.assertEqual(
            startup_presentation(
                is_autostart=True,
                start_in_tray=True,
                tray_available=True,
            ),
            "tray",
        )


if __name__ == "__main__":
    unittest.main()
