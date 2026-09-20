from __future__ import annotations

import argparse
import sys

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QIcon, QPalette
    from PySide6.QtWidgets import QApplication
except ModuleNotFoundError as exc:  # pragma: no cover - user-facing bootstrap path
    if exc.name == "PySide6":
        print(
            "DDS Companion GUI requires PySide6.\n"
            "Run install_gui_dependencies.bat, then run run_companion.bat again.",
            file=sys.stderr,
        )
        raise SystemExit(4) from None
    raise

from dds_companion import __version__
from dds_companion.core.identity import APPLICATION_DISPLAY_NAME, APPLICATION_NAME, resource_path, set_windows_app_user_model_id
from dds_companion.gui.theme import APP_STYLESHEET, BG, TEXT
from dds_companion.gui.window import MainWindow


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DDS Companion desktop interface")
    parser.add_argument("--dds-data", help="Path to DDS_Data")
    parser.add_argument("--app-data", help="DDS Companion runtime data root")
    parser.add_argument("--portable", action="store_true", help="Use Data next to DDS.exe as the Companion data root")
    parser.add_argument("--poll-ms", type=int, default=750)
    parser.add_argument("--settle-ms", type=int, default=500)
    parser.add_argument("--version", action="version", version=f"DDS Companion {__version__}")
    return parser



def make_app_icon() -> QIcon:
    """Load the approved DDS application icon from packaged assets."""
    icon_path = resource_path("assets/DDS.ico")
    icon = QIcon(str(icon_path))
    return icon

def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.poll_ms < 100:
        raise SystemExit("--poll-ms must be at least 100")
    if args.settle_ms < 50:
        raise SystemExit("--settle-ms must be at least 50")

    set_windows_app_user_model_id()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APPLICATION_NAME)
    app.setApplicationDisplayName(APPLICATION_DISPLAY_NAME)
    app.setOrganizationName("DDS")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    app_icon = make_app_icon()
    app.setWindowIcon(app_icon)

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(BG))
    palette.setColor(QPalette.Text, QColor(TEXT))
    app.setPalette(palette)

    window = MainWindow(
        dds_data=args.dds_data,
        app_data=args.app_data,
        portable=args.portable,
        poll_ms=args.poll_ms,
        settle_ms=args.settle_ms,
    )
    window.setWindowIcon(app_icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
