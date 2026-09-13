from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from dds_companion import __version__
from dds_companion.core.paths import build_runtime_paths

from .pages import ActivityPage, DashboardPage, HealthPage, LibraryPage, SettingsPage
from .runtime import GuiRuntime
from .theme import MUTED, TEXT
from .widgets import open_folder, set_state_property


class SignalBus(QObject):
    snapshot = Signal(object)
    activity = Signal(object)
    watch_event = Signal(object)
    runtime_error = Signal(str)
    stopped = Signal()


class MainWindow(QMainWindow):
    PAGE_NAMES = ("Dashboard", "Library", "Activity", "Health", "Settings")

    def __init__(self, *, dds_data: str | None = None, app_data: str | None = None, poll_ms: int = 750, settle_ms: int = 500):
        super().__init__()
        self.setWindowTitle(f"DDS Companion {__version__}")
        self.resize(1320, 840)
        self.setMinimumSize(1080, 680)

        self.bus = SignalBus()
        self.paths = build_runtime_paths(dds_data, app_data)
        self.runtime = GuiRuntime(
            dds_data=dds_data,
            app_data=app_data,
            poll_ms=poll_ms,
            settle_ms=settle_ms,
            snapshot_sink=self.bus.snapshot.emit,
            activity_sink=self.bus.activity.emit,
            watch_sink=self.bus.watch_event.emit,
            error_sink=self.bus.runtime_error.emit,
            stopped_sink=self.bus.stopped.emit,
        )
        self.runtime_thread = threading.Thread(
            target=self.runtime.run,
            name="dds-companion-runtime",
            daemon=True,
        )
        self.latest_snapshot: dict = {
            "paths": {
                "dds_data": str(self.paths.dds_data),
                "app_data": str(self.paths.app_data),
                "database": str(self.paths.database),
                "logs": str(self.paths.logs),
                "cache": str(self.paths.cache),
                "media": str(self.paths.media),
                "backups": str(self.paths.backups),
            }
        }
        self._closing = False

        self._build_ui()
        self._connect_signals()
        self.runtime_thread.start()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(216)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 16, 14, 14)
        side.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel("DDS")
        mark.setObjectName("BrandMark")
        mark.setFixedSize(44, 36)
        mark.setAlignment(Qt.AlignCenter)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("DDS Companion")
        title.setObjectName("BrandTitle")
        subtitle = QLabel(f"v{__version__}")
        subtitle.setObjectName("BrandSub")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand.addWidget(mark)
        brand.addLayout(brand_text, 1)
        side.addLayout(brand)
        side.addSpacing(16)

        self.nav_buttons: list[QPushButton] = []
        for index, name in enumerate(self.PAGE_NAMES):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self.nav_buttons.append(button)
            side.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        side.addStretch(1)

        footer = QFrame()
        footer.setProperty("card", True)
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(11, 10, 11, 10)
        foot.setSpacing(4)
        foot_title = QLabel("LOCAL FIRST")
        foot_title.setObjectName("CardEyebrow")
        foot_text = QLabel("Архив остаётся на этой машине")
        foot_text.setWordWrap(True)
        foot_text.setStyleSheet(f"color:{MUTED};font-size:8.5pt;")
        foot.addWidget(foot_title)
        foot.addWidget(foot_text)
        side.addWidget(footer)
        outer.addWidget(self.sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("Topbar")
        topbar.setFixedHeight(62)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(24, 10, 24, 10)
        top.setSpacing(10)
        self.live_label = QLabel("Запуск Companion…")
        self.live_label.setStyleSheet(f"color:{MUTED};")
        self.live_label.setMaximumWidth(620)
        self.live_label.setToolTip("Последнее живое событие watcher/Activity")
        top.addWidget(self.live_label, 1)

        self.top_open_btn = QPushButton("Open library")
        self.top_open_btn.setProperty("secondary", True)
        self.top_open_btn.clicked.connect(self.open_library)
        top.addWidget(self.top_open_btn)

        self.top_status = QLabel("STARTING")
        self.top_status.setObjectName("StatusPill")
        set_state_property(self.top_status, "STARTING")
        top.addWidget(self.top_status)
        content.addWidget(topbar)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(
            self.runtime.request_refresh,
            self.open_library,
            self.open_dds,
            self.open_logs,
        )
        self.library = LibraryPage(self.open_library)
        self.activity = ActivityPage()
        self.health = HealthPage()
        self.settings = SettingsPage()
        self.pages = [self.dashboard, self.library, self.activity, self.health, self.settings]
        for page in self.pages:
            self.stack.addWidget(page)
        content.addWidget(self.stack, 1)
        outer.addLayout(content, 1)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.status_text = QLabel("Инициализация локального архива…")
        self.status_text.setStyleSheet(f"color:{MUTED};padding-left:8px;")
        status.addWidget(self.status_text, 1)
        self.status_path = QLabel(str(self.paths.app_data))
        self.status_path.setStyleSheet(f"color:{MUTED};padding-right:8px;")
        status.addPermanentWidget(self.status_path)
        self.setStatusBar(status)

    def _connect_signals(self) -> None:
        self.bus.snapshot.connect(self._on_snapshot)
        self.bus.activity.connect(self._on_activity)
        self.bus.watch_event.connect(self._on_watch_event)
        self.bus.runtime_error.connect(self._on_runtime_error)
        self.bus.stopped.connect(self._on_runtime_stopped)

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def _on_snapshot(self, snapshot: dict) -> None:
        self.latest_snapshot = snapshot
        health = snapshot.get("health", {})
        state = health.get("state", "UNKNOWN")
        self.top_status.setText(state)
        set_state_property(self.top_status, state)
        stats = snapshot.get("stats", {})
        self.status_text.setText(
            f"{stats.get('messages', 0)} сообщений · "
            f"{stats.get('guilds', 0)} серверов · "
            f"unresolved failures: {stats.get('failed_jobs_unresolved', 0)}"
        )
        self.status_path.setText(snapshot.get("paths", {}).get("app_data", ""))
        for page in self.pages:
            update = getattr(page, "update_snapshot", None)
            if update:
                update(snapshot)

    def _on_activity(self, event: dict) -> None:
        summary = event.get("summary", "Activity event")
        self.live_label.setText(summary)
        level = event.get("level", "INFO").upper()
        color = {"ERROR": "#ff6b81", "WARNING": "#f0c36a"}.get(level, MUTED)
        self.live_label.setStyleSheet(f"color:{color};")

    def _on_watch_event(self, event: dict) -> None:
        kind = event.get("kind", "event")
        path = Path(event.get("path", ""))
        if kind == "created":
            self.live_label.setText(f"Новый capture · {path.name} · ожидаю settle window")
        elif kind == "changed":
            self.live_label.setText(f"Capture изменился · {path.name} · проверяю стабильность")
        elif kind == "unchanged":
            self.live_label.setText(f"Без изменений · {path.name}")
        self.live_label.setStyleSheet(f"color:{MUTED};")

    def _on_runtime_error(self, message: str) -> None:
        self.top_status.setText("ERROR")
        set_state_property(self.top_status, "ERROR")
        self.live_label.setText(message)
        self.live_label.setStyleSheet("color:#ff6b81;")
        self.status_text.setText("Runtime error — архиватор остановлен")
        QMessageBox.critical(
            self,
            "DDS Companion — Runtime error",
            "Архиватор остановился из-за неожиданной ошибки.\n\n"
            f"{message}\n\n"
            "Существующий архив не удалён. Проверь Health/Logs и перезапусти Companion.",
        )

    def _on_runtime_stopped(self) -> None:
        if self._closing:
            return
        self.status_text.setText("Runtime остановлен")

    def _path(self, key: str) -> str:
        return self.latest_snapshot.get("paths", {}).get(key) or str(getattr(self.paths, key))

    def _open(self, key: str, label: str) -> None:
        ok, detail = open_folder(self._path(key))
        if ok:
            self.statusBar().showMessage(f"{label}: {detail}", 3500)
        else:
            QMessageBox.warning(self, "DDS Companion", detail)

    def open_library(self) -> None:
        self._open("app_data", "Library")

    def open_dds(self) -> None:
        self._open("dds_data", "DDS_Data")

    def open_logs(self) -> None:
        self._open("logs", "Logs")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        self.status_text.setText("Останавливаю watcher…")
        self.runtime.stop()
        if self.runtime_thread.is_alive():
            self.runtime_thread.join(timeout=1.8)
        event.accept()
