from __future__ import annotations

import ctypes
import os
import sqlite3
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication, QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QFileDialog,
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
from dds_companion.core.identity import APPLICATION_DISPLAY_NAME, resource_path
from dds_companion.core.paths import build_runtime_paths, default_manual_export_path
from dds_companion.core.settings import SettingsStore
from dds_companion.services.archive_reset_service import reset_local_archive
from dds_companion.services.activity_service import ActivityService
from dds_companion.services.branch_maintenance_service import BranchMaintenanceService
from dds_companion.services.export_package_service import ExportPackageService
from dds_companion.services.media_cache_service import MediaCacheService
from dds_companion.storage.database import connect_database
from dds_companion.updater.controller import UpdateController
from dds_companion.updater.installer_launcher import launch_external_updater
from dds_companion.updater.paths import build_updater_paths
from dds_companion.updater.pointer import atomic_write_json, read_json

from .layout_profile import choose_layout_profile
from .pages import ActivityPage, DashboardPage, HealthPage, LibraryPage, SettingsPage
from .runtime import GuiRuntime
from .theme import MUTED, TEXT
from .widgets import human_activity_summary, open_folder, set_state_property


class SignalBus(QObject):
    snapshot = Signal(object)
    activity = Signal(object)
    watch_event = Signal(object)
    runtime_error = Signal(str)
    stopped = Signal()
    runtime_ready = Signal()
    maintenance_done = Signal(object)
    library_messages = Signal(object)
    update_status = Signal(object)


class MainWindow(QMainWindow):
    startup_ready = Signal()

    PAGE_NAMES = ("Dashboard", "Library", "Activity", "Health", "Settings")
    PAGE_LABELS = ("Главная", "Библиотека", "Активность", "Статус", "Настройки")

    def __init__(self, *, dds_data: str | None = None, app_data: str | None = None, portable: bool = False, poll_ms: int = 750, settle_ms: int = 500):
        super().__init__()
        self.setWindowTitle(APPLICATION_DISPLAY_NAME)
        self.setMinimumSize(960, 600)
        self._layout_profile: str | None = None
        self._screen_signals_connected = False
        self._observed_screen = None
        self._startup_foreground_attempted = False
        self._startup_ready_emitted = False
        self._update_install_launched = False

        self.bus = SignalBus()
        self.paths = build_runtime_paths(dds_data, app_data, portable=portable)
        self.settings_store = SettingsStore(self.paths.settings)
        self.update_paths = build_updater_paths(self.paths)
        self.update_controller = UpdateController(
            paths=self.update_paths,
            current_version=__version__,
            settings_getter=lambda: self.settings_store.settings,
            status_sink=self.bus.update_status.emit,
        )
        self.media_cache = MediaCacheService(self.paths.media, self.paths.database)
        self._last_diagnostics_report = ""
        self._runtime_kwargs = {
            "dds_data": dds_data,
            "app_data": app_data,
            "portable": portable,
            "poll_ms": poll_ms,
            "settle_ms": settle_ms,
        }
        self.runtime: GuiRuntime | None = None
        self.runtime_thread: threading.Thread | None = None
        self._archive_reset_in_progress = False
        self._branch_maintenance_in_progress = False
        self._manual_export_in_progress = False
        self.clear_cache_worker_active = False
        self.latest_snapshot: dict = {
            "paths": {
                "dds_data": str(self.paths.dds_data),
                "app_data": str(self.paths.app_data),
                "database": str(self.paths.database),
                "logs": str(self.paths.logs),
                "cache": str(self.paths.cache),
                "media": str(self.paths.media),
                "backups": str(self.paths.backups),
                "config": str(self.paths.config),
                "settings": str(self.paths.settings),
                "deployment_profile": self.paths.deployment_profile,
                "application_dir": str(self.paths.application_dir or ""),
            },
            "settings": self.settings_store.snapshot(),
        }
        self._closing = False

        self._build_ui()
        self._connect_signals()
        self._size_for_primary_screen()
        self._apply_layout_profile(force=True)
        self._start_runtime()
        self._run_cache_policy_async("startup")
        QTimer.singleShot(2500, self._maybe_background_update_check)

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
        brand.setSpacing(12)
        mark = QLabel()
        mark.setObjectName("BrandMark")
        mark.setFixedSize(48, 48)
        mark.setAlignment(Qt.AlignCenter)
        brand_pixmap = QPixmap(str(resource_path("assets/DDS_app_icon_master.png")))
        if not brand_pixmap.isNull():
            mark.setPixmap(brand_pixmap.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            mark.setText("DDS")
        brand_text = QVBoxLayout()
        brand_text.setSpacing(2)
        title = QLabel("DDS")
        title.setObjectName("BrandTitle")
        title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        subtitle = QLabel("Discord\nData\nSnatcher")
        subtitle.setObjectName("BrandSub")
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        brand_text.addWidget(title)
        brand_text.addSpacing(3)
        brand_text.addWidget(subtitle)
        brand.addWidget(mark, 0, Qt.AlignTop)
        brand.addLayout(brand_text, 1)
        side.addLayout(brand)
        side.addSpacing(22)

        self.nav_buttons: list[QPushButton] = []
        for index, name in enumerate(self.PAGE_LABELS):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self.nav_buttons.append(button)
            side.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        side.addStretch(1)

        outer.addWidget(self.sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self.topbar = QFrame()
        topbar = self.topbar
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

        self.top_status = QPushButton("STARTING")
        self.top_status.setObjectName("StatusPill")
        self.top_status.setCursor(Qt.PointingHandCursor)
        self.top_status.clicked.connect(self._open_health_from_status)
        set_state_property(self.top_status, "STARTING")
        top.addWidget(self.top_status)
        content.addWidget(topbar)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.library = LibraryPage(
            on_messages_requested=self._request_library_messages,
            on_export_rule_changed=self._change_export_rule,
            on_scope_action=self._library_scope_action,
        )
        self.activity = ActivityPage()
        self.health = HealthPage(
            on_media_retry=self._retry_media_issue,
            on_media_ignore=self._ignore_media_issue,
            on_media_ignore_all=self._ignore_all_media_issues,
            on_media_clear_processed=self._clear_processed_media_issues,
        )
        self.settings = SettingsPage(
            on_setting_changed=self._on_setting_changed,
            on_clear_media_cache=self._clear_media_cache,
            on_reset_local_archive=self._reset_local_archive,
            on_choose_export_folder=self._choose_export_folder,
            on_check_updates=self._check_updates_manual,
            on_download_update=self._download_update,
            on_install_update=self._install_update_now,
            on_cancel_update=self._cancel_update,
            on_run_diagnostics=self._run_diagnostics,
            on_database_check=self._database_quick_check,
            on_copy_report=self._copy_diagnostics_report,
        )
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

    def _size_for_primary_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1320, 840)
            return
        geometry = screen.availableGeometry()
        profile = choose_layout_profile(
            available_width=geometry.width(),
            available_height=geometry.height(),
            logical_dpi=screen.logicalDotsPerInch(),
            device_pixel_ratio=screen.devicePixelRatio(),
            window_width=geometry.width(),
        )
        desired = {
            "compact": (1240, 700),
            "standard": (1320, 840),
            "large": (1500, 940),
        }[profile]
        width = min(desired[0], max(self.minimumWidth(), int(geometry.width() * 0.94)))
        height = min(desired[1], max(self.minimumHeight(), int(geometry.height() * 0.94)))
        self.resize(width, height)

    def _current_screen(self):
        return self.screen() or QGuiApplication.primaryScreen()

    def _apply_layout_profile(self, *, force: bool = False) -> None:
        screen = self._current_screen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        profile = choose_layout_profile(
            available_width=geometry.width(),
            available_height=geometry.height(),
            logical_dpi=screen.logicalDotsPerInch(),
            device_pixel_ratio=screen.devicePixelRatio(),
            window_width=self.width(),
        )
        if not force and profile == self._layout_profile:
            return
        self._layout_profile = profile

        if profile == "compact":
            self.sidebar.setFixedWidth(210)
            self.topbar.setFixedHeight(54)
        elif profile == "large":
            self.sidebar.setFixedWidth(236)
            self.topbar.setFixedHeight(68)
        else:
            self.sidebar.setFixedWidth(216)
            self.topbar.setFixedHeight(62)

        for page in self.pages:
            apply_profile = getattr(page, "apply_layout_profile", None)
            if apply_profile:
                apply_profile(profile)

    def _bind_screen(self, screen) -> None:
        if screen is None or screen is self._observed_screen:
            return
        self._observed_screen = screen
        screen.availableGeometryChanged.connect(lambda _rect: self._apply_layout_profile(force=True))
        screen.logicalDotsPerInchChanged.connect(lambda _dpi: self._apply_layout_profile(force=True))

    def _on_screen_changed(self, screen) -> None:
        self._bind_screen(screen)
        self._apply_layout_profile(force=True)

    def _connect_screen_signals(self) -> None:
        if self._screen_signals_connected:
            return
        handle = self.windowHandle()
        if handle is None:
            return
        handle.screenChanged.connect(self._on_screen_changed)
        self._bind_screen(handle.screen())
        self._screen_signals_connected = True

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._connect_screen_signals()
        self._apply_layout_profile(force=True)
        # Explorer can keep focus when launching a .bat/.pyw chain on Windows.
        # Request foreground exactly once, after the native window exists. The
        # guard prevents later show/unminimize events from ever stealing focus.
        if not self._startup_foreground_attempted:
            QTimer.singleShot(75, self._bring_to_front_once)

    def _bring_to_front_once(self) -> None:
        """Bring the main window forward once at startup, never afterwards."""
        if self._startup_foreground_attempted:
            return
        self._startup_foreground_attempted = True
        self._request_foreground()

    def activate_from_secondary_launch(self) -> None:
        """Activate the existing window when a second DDS launch is attempted."""
        self._request_foreground()

    def _request_foreground(self) -> None:
        """Show/restore this window and request foreground without changing its normal mode."""
        if not self.isVisible():
            self.show()

        state = self.windowState()
        if state & Qt.WindowMinimized:
            # Remove only the minimized bit. Preserve maximized/fullscreen state.
            self.setWindowState((state & ~Qt.WindowMinimized) | Qt.WindowActive)
            self.show()

        self.raise_()
        self.activateWindow()

        if sys.platform != "win32":
            return

        # Windows fallback. TOPMOST is toggled only for the activation request and
        # removed immediately; Companion is never kept Always-on-Top.
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_SHOWWINDOW = 0x0040
            flags = SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            # Foreground polish must never destabilize Companion.
            pass

    def capture_update_resume_state(self, path: str | Path) -> Path:
        geometry = self.geometry()
        if self.isFullScreen():
            presentation = "fullscreen"
        elif self.isMaximized():
            presentation = "maximized"
        elif self.isMinimized():
            presentation = "minimized"
        elif not self.isVisible():
            presentation = "hidden"
        else:
            presentation = "normal"
        payload = {
            "schema": "dds-window-resume-v1",
            "presentation": presentation,
            "geometry": {
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
            },
            "page_index": self.stack.currentIndex(),
            "hidden_to_tray": False,
        }
        return atomic_write_json(path, payload)

    def restore_update_resume_state(self, path: str | Path) -> None:
        try:
            payload = read_json(path)
            if payload.get("schema") != "dds-window-resume-v1":
                return
            geometry = payload.get("geometry") or {}
            width = max(self.minimumWidth(), int(geometry.get("width", self.width())))
            height = max(self.minimumHeight(), int(geometry.get("height", self.height())))
            self.setGeometry(
                int(geometry.get("x", self.x())),
                int(geometry.get("y", self.y())),
                width,
                height,
            )
            page_index = int(payload.get("page_index", 0))
            if 0 <= page_index < self.stack.count():
                self._select_page(page_index)
            presentation = str(payload.get("presentation") or "normal")
            if bool(payload.get("hidden_to_tray")) or presentation == "hidden":
                self.hide()
            elif presentation == "fullscreen":
                self.showFullScreen()
            elif presentation == "maximized":
                self.showMaximized()
            elif presentation == "minimized":
                self.showMinimized()
            else:
                self.showNormal()
        except Exception:
            # Resume QoL must never prevent a healthy version from starting.
            return

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_layout_profile()

    def _connect_signals(self) -> None:
        self.bus.snapshot.connect(self._on_snapshot)
        self.bus.activity.connect(self._on_activity)
        self.bus.watch_event.connect(self._on_watch_event)
        self.bus.runtime_error.connect(self._on_runtime_error)
        self.bus.stopped.connect(self._on_runtime_stopped)
        self.bus.runtime_ready.connect(self._on_runtime_ready)
        self.bus.maintenance_done.connect(self._on_maintenance_done)
        self.bus.library_messages.connect(self.library.set_message_page)
        self.bus.update_status.connect(self._on_update_status)

    def _new_runtime(self) -> GuiRuntime:
        return GuiRuntime(
            **self._runtime_kwargs,
            snapshot_sink=self.bus.snapshot.emit,
            activity_sink=self.bus.activity.emit,
            watch_sink=self.bus.watch_event.emit,
            error_sink=self.bus.runtime_error.emit,
            stopped_sink=self.bus.stopped.emit,
            ready_sink=self.bus.runtime_ready.emit,
            library_message_sink=self.bus.library_messages.emit,
        )

    def _start_runtime(self) -> None:
        if self._closing:
            return
        if self.runtime_thread is not None and self.runtime_thread.is_alive():
            return
        self.runtime = self._new_runtime()
        self.runtime_thread = threading.Thread(
            target=self.runtime.run,
            name="dds-companion-runtime",
            daemon=True,
        )
        self.status_text.setText("Инициализация локального архива…")
        self.runtime_thread.start()

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == self.PAGE_NAMES.index("Dashboard"):
            if self.runtime is not None:
                self.runtime.request_refresh()
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        on_health = index == self.PAGE_NAMES.index("Health")
        self.top_status.setEnabled(not on_health)
        self.top_status.setToolTip(
            "Текущая страница Статус" if on_health else "Открыть Статус"
        )

    def _open_health_from_status(self) -> None:
        health_index = self.PAGE_NAMES.index("Health")
        if self.stack.currentIndex() != health_index:
            self._select_page(health_index)

    def _on_snapshot(self, snapshot: dict) -> None:
        snapshot = dict(snapshot)
        settings_snapshot = self.settings_store.snapshot()
        settings_snapshot["effective_manual_export_path"] = str(self._effective_manual_export_path())
        snapshot["settings"] = settings_snapshot
        self.latest_snapshot = snapshot
        health = snapshot.get("health", {})
        state = health.get("state", "UNKNOWN")
        self.top_status.setText(state)
        set_state_property(self.top_status, state)
        if self.stack.currentIndex() != self.PAGE_NAMES.index("Health"):
            detail = health.get("tooltip") or health.get("summary") or state
            self.top_status.setToolTip(f"{detail}\nНажмите, чтобы открыть Статус")
        stats = snapshot.get("stats", {})
        self.status_text.setText(
            f"{stats.get('messages', 0)} сообщений · "
            f"{stats.get('guilds', 0)} серверов · "
            f"ошибок импорта: {stats.get('failed_jobs_unresolved', 0)}"
        )
        self.status_path.setText(snapshot.get("paths", {}).get("app_data", ""))
        for page in self.pages:
            update = getattr(page, "update_snapshot", None)
            if update:
                update(snapshot)
        # A snapshot is also a valid readiness signal, retained as a fallback.
        self._mark_startup_ready()

    def _on_runtime_ready(self) -> None:
        self._mark_startup_ready()

    def _mark_startup_ready(self) -> None:
        if self._startup_ready_emitted:
            return
        self._startup_ready_emitted = True
        self.startup_ready.emit()

    def _on_activity(self, event: dict) -> None:
        summary = human_activity_summary(event)
        self.live_label.setText(summary)
        level = event.get("level", "INFO").upper()
        color = {"ERROR": "#ff6b81", "WARNING": "#f0c36a"}.get(level, MUTED)
        self.live_label.setStyleSheet(f"color:{color};")

    def _on_watch_event(self, event: dict) -> None:
        kind = event.get("kind", "event")
        path = Path(event.get("path", ""))
        if kind == "created":
            self.live_label.setText(f"Новый файл захвата · {path.name} · жду стабилизации")
        elif kind == "changed":
            self.live_label.setText(f"Файл захвата изменился · {path.name} · проверяю стабильность")
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
            "DDS — Runtime error",
            "Архиватор остановился из-за неожиданной ошибки.\n\n"
            f"{message}\n\n"
            "Существующий архив не удалён. Проверь Health/Logs и перезапусти Companion.",
        )

    def _on_runtime_stopped(self) -> None:
        if self._closing or self._archive_reset_in_progress:
            return
        self.status_text.setText("Runtime остановлен")


    def _request_library_messages(self, request: dict) -> None:
        if self.runtime is not None:
            self.runtime.request_library_messages(request)

    def _change_export_rule(self, scope_kind: str, scope_id: str, mode: str) -> None:
        if self.runtime is None:
            return
        self.runtime.request_export_rule_change(scope_kind, scope_id, mode)
        label = {
            "INCLUDE": "Выгружать",
            "EXCLUDE": "Не выгружать",
        }.get(str(mode).upper(), str(mode))
        self.statusBar().showMessage(f"Правило выгрузки: {label}", 2500)

    def _effective_manual_export_path(self) -> Path:
        configured = self.settings_store.settings.manual_export_path
        if configured:
            return Path(configured).expanduser().resolve()
        return default_manual_export_path(self.paths).expanduser().resolve()

    def _choose_export_folder(self) -> None:
        initial = self._effective_manual_export_path()
        initial.mkdir(parents=True, exist_ok=True)
        selected = QFileDialog.getExistingDirectory(
            self,
            "DDS — Папка ручного экспорта",
            str(initial),
        )
        if not selected:
            return
        try:
            self.settings_store.update(manual_export_path=str(Path(selected).expanduser().resolve()))
        except Exception as exc:
            QMessageBox.warning(self, "DDS", f"Не удалось сохранить папку экспорта:\n{exc}")
            return
        self._refresh_settings_surface()
        self.statusBar().showMessage("Папка ручного экспорта сохранена", 3000)

    def _library_scope_action(self, action: str, detail: dict) -> None:
        kind = str(detail.get("kind") or "")
        scope_id = str(detail.get("id") or "")
        name = str(detail.get("name") or scope_id or "раздел")
        if not kind or not scope_id:
            return
        if action in {"package_text", "package_text_cache"}:
            mode = "TEXT_ONLY" if action == "package_text" else "TEXT_AND_CACHE"
            self._package_scope(kind, scope_id, name, mode)
            return

        if self._branch_maintenance_in_progress or self._archive_reset_in_progress:
            self.statusBar().showMessage("Сначала дождись завершения текущего обслуживания DDS", 4000)
            return

        if action == "clear_branch_media":
            prompt = (
                f"Очистить локальный медиакэш раздела «{name}»?\n\n"
                "Сообщения, ссылки, структура и правила выгрузки останутся."
            )
            title = "DDS — Очистка медиакэша ветки"
        elif action == "delete_branch_data":
            prompt = (
                f"Удалить архивные данные раздела «{name}»?\n\n"
                "Сообщения и связанные вложения будут удалены. Сам узел Библиотеки "
                "и его правило выгрузки сохранятся."
            )
            title = "DDS — Удаление данных ветки"
        elif action == "delete_branch":
            prompt = (
                f"ПОЛНОСТЬЮ удалить раздел «{name}» из локального архива?\n\n"
                "Будут удалены данные, медиакэш, структурный узел и правила выгрузки. "
                "Для канала/сервера удаляются и дочерние разделы.\n\nОтменить это действие нельзя."
            )
            title = "DDS — Полное удаление ветки"
        else:
            return
        answer = QMessageBox.warning(
            self, title, prompt, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        self._run_branch_maintenance(action, kind, scope_id, name)

    def _package_scope(self, kind: str, scope_id: str, name: str, mode: str) -> None:
        if self._manual_export_in_progress:
            self.statusBar().showMessage("Уже создаётся другой ZIP-пакет", 3500)
            return
        self._manual_export_in_progress = True
        output_dir = self._effective_manual_export_path()
        self.statusBar().showMessage(f"Упаковываю «{name}»…", 0)

        def worker() -> None:
            connection = None
            try:
                connection = connect_database(self.paths.database)
                result = ExportPackageService(connection, self.paths.media).package(
                    kind, scope_id, mode=mode, output_dir=output_dir, app_version=__version__
                )
                ActivityService(connection).publish(
                    subsystem="export",
                    event_type="manual_export_created",
                    summary=f"Manual export created: {result.scope_name}",
                    details=result.to_dict(),
                    guild_id=scope_id if kind == "guild" else None,
                    parent_channel_id=scope_id if kind == "channel" else None,
                    thread_id=scope_id if kind == "thread" else None,
                )
                self.bus.maintenance_done.emit({"kind": "manual_export", "ok": True, "result": result.to_dict()})
            except Exception as exc:
                if connection is not None:
                    try:
                        ActivityService(connection).publish(
                            level="ERROR", subsystem="export", event_type="manual_export_failed",
                            summary=f"Manual export failed: {name}",
                            details={"scope_kind": kind, "scope_id": scope_id, "error": f"{type(exc).__name__}: {exc}"},
                        )
                    except Exception:
                        pass
                self.bus.maintenance_done.emit({
                    "kind": "manual_export", "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass

        threading.Thread(target=worker, name="dds-manual-export", daemon=True).start()

    def _run_branch_maintenance(self, action: str, kind: str, scope_id: str, name: str) -> None:
        self._branch_maintenance_in_progress = True
        runtime = self.runtime
        thread = self.runtime_thread
        self.status_text.setText(f"Останавливаю DDS для безопасного обслуживания «{name}»…")
        if runtime is not None:
            runtime.stop()
            runtime.request_media_wake()

        def worker() -> None:
            connection = None
            try:
                if thread is not None and thread.is_alive():
                    thread.join(timeout=10.0)
                if thread is not None and thread.is_alive():
                    raise RuntimeError("runtime did not stop within 10 seconds; branch was not touched")
                connection = connect_database(self.paths.database)
                service = BranchMaintenanceService(connection, self.paths.media)
                if action == "clear_branch_media":
                    result = service.clear_media_cache(kind, scope_id)
                    event_type = "branch_media_cache_cleared"
                elif action == "delete_branch_data":
                    result = service.delete_data(kind, scope_id)
                    event_type = "branch_data_deleted"
                else:
                    result = service.delete_branch(kind, scope_id)
                    event_type = "branch_deleted"
                ActivityService(connection).publish(
                    subsystem="archive", event_type=event_type,
                    summary=f"{event_type}: {name}", details=result.to_dict(),
                )
                self.bus.maintenance_done.emit({
                    "kind": "branch_maintenance", "ok": result.errors == 0,
                    "action": action, "name": name, "result": result.to_dict(),
                })
            except Exception as exc:
                self.bus.maintenance_done.emit({
                    "kind": "branch_maintenance", "ok": False,
                    "action": action, "name": name,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass

        threading.Thread(target=worker, name="dds-branch-maintenance", daemon=True).start()

    def _retry_media_issue(self, media_key: str) -> None:
        runtime = self.runtime
        if not media_key or runtime is None:
            return
        runtime.request_media_retry(media_key)
        self.statusBar().showMessage("Повторная загрузка медиа запущена…", 3500)
        runtime.request_refresh()

    def _ignore_media_issue(self, media_key: str) -> None:
        runtime = self.runtime
        if not media_key or runtime is None:
            return
        runtime.request_media_ignore(media_key)
        self.statusBar().showMessage("Проблема медиа помечена как игнорируемая", 3500)
        runtime.request_refresh()

    def _ignore_all_media_issues(self) -> None:
        runtime = self.runtime
        if runtime is None:
            return
        runtime.request_media_ignore_all()
        self.statusBar().showMessage("Все текущие проблемы медиа помечены как обработанные", 3500)
        runtime.request_refresh()

    def _clear_processed_media_issues(self) -> None:
        runtime = self.runtime
        if runtime is None:
            return
        runtime.request_media_clear_processed()
        self.statusBar().showMessage(
            "Обработанные медиа переведены в ожидание переобнаружения", 4000
        )
        runtime.request_refresh()

    @property
    def startup_is_ready(self) -> bool:
        return self._startup_ready_emitted

    def _update_relaunch_args(self) -> list[str]:
        args: list[str] = []
        if self._runtime_kwargs.get("dds_data"):
            args += ["--dds-data", str(self._runtime_kwargs["dds_data"])]
        if self._runtime_kwargs.get("app_data"):
            args += ["--app-data", str(self._runtime_kwargs["app_data"])]
        if self._runtime_kwargs.get("portable"):
            args.append("--portable")
        args += ["--poll-ms", str(self._runtime_kwargs["poll_ms"])]
        args += ["--settle-ms", str(self._runtime_kwargs["settle_ms"])]
        return args

    def _check_updates_manual(self) -> None:
        self.update_controller.check_async(manual=True)

    def _download_update(self) -> None:
        self.update_controller.download_async()

    def _install_update_now(self) -> None:
        self._launch_prepared_update(close_after=True)

    def _cancel_update(self) -> None:
        if not self.update_controller.cancel_current():
            self.statusBar().showMessage("Нет активной операции обновления.", 2500)

    def _launch_prepared_update(self, *, close_after: bool) -> bool:
        prepared = self.update_controller.prepared
        if prepared is None:
            QMessageBox.information(self, "DDS", "Сначала загрузите и проверьте обновление.")
            return False
        if self._update_install_launched:
            return True
        try:
            resume_state = self.update_paths.workspace / "resume_state.json"
            self.capture_update_resume_state(resume_state)
            launch_external_updater(
                application_dir=self.paths.application_dir,
                paths=self.update_paths,
                prepared=prepared,
                parent_pid=os.getpid(),
                resume_state_path=resume_state,
                launch_args=self._update_relaunch_args(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "DDS", f"Не удалось запустить updater:\n{type(exc).__name__}: {exc}")
            return False
        self._update_install_launched = True
        self.statusBar().showMessage("Updater запущен. DDS будет перезапущен после установки.", 7000)
        if close_after:
            self.close()
        return True

    def _maybe_background_update_check(self) -> None:
        if not self._closing:
            self.update_controller.maybe_check_in_background()

    def _on_update_status(self, payload: dict) -> None:
        self.settings.set_update_status(payload)
        state = str(payload.get("state") or "")
        message = str(payload.get("message") or "")
        if state in {"CHECKING", "CURRENT", "AVAILABLE", "ERROR"} and self.runtime is not None:
            # Health/Status observes updater check_state.json on the runtime
            # thread. Force a snapshot so manual checks become visible at once.
            self.runtime.request_refresh()
        if state in {"AVAILABLE", "STAGED", "ERROR"} and message:
            self.statusBar().showMessage(message, 6000)
        if state == "STAGED" and bool(payload.get("auto_install")):
            self.settings.set_update_status({
                **payload,
                "message": message + " Автоустановка выполнится при выходе из DDS.",
            })

    def _on_setting_changed(self, key: str, value) -> None:
        try:
            self.settings_store.update(**{key: value})
        except Exception as exc:
            QMessageBox.warning(self, "DDS", f"Не удалось сохранить настройку:\n{exc}")
            return
        self.statusBar().showMessage("Настройка сохранена", 2500)
        self._refresh_settings_surface()
        if key == "update_background_check_enabled" and bool(value):
            QTimer.singleShot(0, self._maybe_background_update_check)
        if key == "media_autodownload_enabled" and self.runtime is not None:
            self.runtime.request_media_autodownload_change(bool(value))
        if key in {"media_cache_limit_bytes", "media_max_file_bytes", "media_retention_days"}:
            self._run_cache_policy_async("settings")

    def _refresh_settings_surface(self) -> None:
        if not self.latest_snapshot:
            return
        snapshot = dict(self.latest_snapshot)
        settings_snapshot = self.settings_store.snapshot()
        settings_snapshot["effective_manual_export_path"] = str(self._effective_manual_export_path())
        snapshot["settings"] = settings_snapshot
        self.latest_snapshot = snapshot
        self.settings.update_snapshot(snapshot)

    def _run_cache_policy_async(self, reason: str) -> None:
        settings = self.settings_store.settings

        def worker() -> None:
            try:
                result = self.media_cache.enforce(settings)
                self.bus.maintenance_done.emit({
                    "kind": "cache_policy",
                    "reason": reason,
                    "ok": result.errors == 0,
                    "result": result.to_dict(),
                })
            except Exception as exc:
                self.bus.maintenance_done.emit({
                    "kind": "cache_policy",
                    "reason": reason,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        threading.Thread(target=worker, name="dds-cache-policy", daemon=True).start()

    def _reset_local_archive(self) -> None:
        if self._archive_reset_in_progress:
            return
        answer = QMessageBox.warning(
            self,
            "DDS — Сброс локального архива",
            "Будут безвозвратно удалены все сохранённые сообщения, ссылки и локально загруженные медиа.\n\n"
            "Настройки DDS и исходные DDS_Data сохранятся. Уже существующие capture-файлы не будут импортированы заново, пока Plugin не обновит их после сброса.\n\n"
            "Начать с чистого локального архива?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self._archive_reset_in_progress = True
        self.settings.reset_archive_button.setEnabled(False)
        self.status_text.setText("Останавливаю DDS для безопасного сброса архива…")
        runtime = self.runtime
        thread = self.runtime_thread
        if runtime is not None:
            runtime.stop()
            runtime.request_media_wake()

        def worker() -> None:
            try:
                if thread is not None and thread.is_alive():
                    thread.join(timeout=10.0)
                if thread is not None and thread.is_alive():
                    raise RuntimeError("runtime did not stop within 10 seconds; archive was not touched")
                result = reset_local_archive(self.paths)
                self.bus.maintenance_done.emit({
                    "kind": "archive_reset",
                    "ok": True,
                    "result": result.to_dict(),
                })
            except Exception as exc:
                self.bus.maintenance_done.emit({
                    "kind": "archive_reset",
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        threading.Thread(target=worker, name="dds-archive-reset", daemon=True).start()

    def _clear_media_cache(self) -> None:
        if int(self.latest_snapshot.get("stats", {}).get("media_bytes", 0)) <= 0:
            self.statusBar().showMessage("Media cache уже пуст", 2500)
            return
        if self.settings_store.settings.confirm_media_cache_clear:
            answer = QMessageBox.question(
                self,
                "DDS — Очистка медиакэша",
                "Удалить только локальные media-файлы из cache?\n\n"
                "SQLite, DDS JSON, сообщения и attachment metadata останутся нетронутыми.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self.clear_cache_worker_active = True
        self.settings.clear_media_button.setEnabled(False)
        self.settings.set_diagnostic_status("Очистка media cache…", report_available=bool(self._last_diagnostics_report))

        def worker() -> None:
            try:
                result = self.media_cache.clear()
                self.bus.maintenance_done.emit({
                    "kind": "cache_clear",
                    "ok": result.errors == 0,
                    "result": result.to_dict(),
                })
            except Exception as exc:
                self.bus.maintenance_done.emit({
                    "kind": "cache_clear",
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        threading.Thread(target=worker, name="dds-cache-clear", daemon=True).start()

    def _on_maintenance_done(self, payload: dict) -> None:
        kind = payload.get("kind")
        ok = bool(payload.get("ok"))
        result = payload.get("result") or {}
        error = payload.get("error")

        if kind == "archive_reset":
            self._archive_reset_in_progress = False
            if ok:
                self.latest_snapshot = {
                    "paths": self.latest_snapshot.get("paths", {}),
                    "settings": self.settings_store.snapshot(),
                }
                self.library._library = []
                self.library.rebuild()
                self._start_runtime()
                self.statusBar().showMessage("Локальный архив сброшен. DDS начал новую чистую историю.", 6500)
            else:
                self.settings.reset_archive_button.setEnabled(True)
                QMessageBox.critical(
                    self,
                    "DDS — Сброс архива",
                    f"Сброс архива отменён из-за ошибки. Исходные данные не удаляются принудительно.\n\n{error or result}",
                )
                self._start_runtime()
        elif kind == "manual_export":
            self._manual_export_in_progress = False
            if ok:
                output = Path(str(result.get("output_path") or ""))
                missing = int(result.get("media_missing", 0) or 0)
                self.statusBar().showMessage(
                    f"ZIP готов: {output.name} · {result.get('message_count', 0)} сообщений"
                    + (f" · {missing} медиа не включено" if missing else ""),
                    7000,
                )
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Information)
                box.setWindowTitle("DDS — Экспорт готов")
                box.setText(f"Пакет создан:\n{output}")
                box.setInformativeText(
                    f"Сообщений: {result.get('message_count', 0)} · "
                    f"медиа: {result.get('media_included', 0)}/{result.get('media_total', 0)} включено"
                )
                open_button = box.addButton("Открыть папку", QMessageBox.ActionRole)
                box.addButton(QMessageBox.Ok)
                box.exec()
                if box.clickedButton() is open_button:
                    open_folder(output.parent)
            else:
                QMessageBox.warning(self, "DDS — Экспорт", f"Не удалось создать ZIP:\n{error or result}")
        elif kind == "branch_maintenance":
            self._branch_maintenance_in_progress = False
            self._start_runtime()
            if ok:
                action = payload.get("action")
                labels = {
                    "clear_branch_media": "Медиакэш ветки очищен",
                    "delete_branch_data": "Данные ветки удалены",
                    "delete_branch": "Ветка полностью удалена",
                }
                self.statusBar().showMessage(labels.get(action, "Операция завершена"), 6000)
            else:
                QMessageBox.warning(
                    self, "DDS — Обслуживание ветки",
                    f"Операция завершилась с ошибкой. DDS будет перезапущен.\n\n{error or result}",
                )
        elif kind == "cache_clear":
            self.clear_cache_worker_active = False
            if ok:
                removed = result.get("files_removed", 0)
                bytes_removed = result.get("bytes_removed", 0)
                self.statusBar().showMessage(
                    f"Media cache очищен: {removed} файлов, {bytes_removed} bytes", 5000
                )
                if self.runtime is not None:
                    self.runtime.request_media_wake()
            else:
                QMessageBox.warning(self, "DDS", f"Очистка cache завершилась с ошибкой:\n{error or result}")
        elif kind == "cache_policy" and payload.get("reason") != "startup":
            removed = result.get("files_removed", 0)
            if removed:
                self.statusBar().showMessage(
                    f"Media cache policy применена: удалено {removed} файлов", 4000
                )
            elif not ok:
                self.statusBar().showMessage(f"Cache policy warning: {error or result}", 5000)
        elif kind == "db_check":
            text = payload.get("message") or ("PASS" if ok else "FAILED")
            self.settings.set_database_check_status(text)
            self.statusBar().showMessage(f"Database quick check: {text}", 4000)

        if self.runtime is not None:
            self.runtime.request_refresh()

    def _run_diagnostics(self) -> None:
        snapshot = self.latest_snapshot or {}
        health = snapshot.get("health", {})
        stats = snapshot.get("stats", {})
        paths = snapshot.get("paths", {})
        subs = health.get("subsystems", {})
        lines = [
            "DDS — System report",
            f"Companion: {snapshot.get('version', __version__)}",
            f"Overall Health: {health.get('state', 'UNKNOWN')}",
            f"Plugin: {subs.get('plugin', {}).get('state', 'UNKNOWN')}",
            f"Discord: {subs.get('discord', {}).get('state', 'UNKNOWN')}",
            f"Database: {subs.get('database', {}).get('state', 'UNKNOWN')}",
            f"DDS_Data: {subs.get('dds_data', {}).get('state', 'UNKNOWN')}",
            f"Watcher: {subs.get('watcher', {}).get('state', 'UNKNOWN')}",
            f"Media Backfill: {subs.get('media', {}).get('state', 'UNKNOWN')}",
            f"Messages: {stats.get('messages', 0)}",
            f"Media total/known/cached: {stats.get('total_media', 0)} / {stats.get('known_media', 0)} / {stats.get('cached_media_files', 0)}",
            f"Media queued/downloading: {stats.get('media_queued', 0)} / {stats.get('media_downloading', 0)}",
            f"Media retry/stale/failed: {stats.get('media_retryable_failed', 0)} / {stats.get('media_stale_url', 0)} / {stats.get('media_permanent_failed', 0)}",
            f"Media attention/ignored/unresolved: {stats.get('media_attention', 0)} / {stats.get('media_ignored', 0)} / {stats.get('media_unresolved', 0)}",
            f"Storage bytes: {stats.get('total_known_storage_bytes', 0)}",
            f"SQLite bytes: {stats.get('sqlite_bytes', 0)}",
            f"DDS JSON bytes: {stats.get('dds_json_bytes', 0)}",
            f"Media cache bytes: {stats.get('media_bytes', 0)}",
            f"Unresolved failures: {stats.get('failed_jobs_unresolved', 0)}",
            f"DDS_Data path: {paths.get('dds_data', '—')}",
            f"App data path: {paths.get('app_data', '—')}",
            f"Settings path: {self.paths.settings}",
            f"Deployment profile: {paths.get('deployment_profile', self.paths.deployment_profile)}",
            f"Application dir: {paths.get('application_dir', str(self.paths.application_dir or '—'))}",
        ]
        media_details = (subs.get("media", {}) or {}).get("details", {}) or {}
        rediscovery_items = list(media_details.get("rediscovery_items") or [])
        if rediscovery_items:
            lines.append("")
            lines.append(f"Awaiting media rediscovery: {len(rediscovery_items)} item(s) shown")
            for item in rediscovery_items[:50]:
                lines.append(
                    "  - "
                    f"{item.get('filename') or 'без имени'} | "
                    f"state={item.get('state') or 'UNRESOLVED'} | "
                    f"HTTP={item.get('http_status') if item.get('http_status') is not None else '—'} | "
                    f"class={item.get('failure_class') or '—'} | "
                    f"updated={item.get('updated_at') or '—'} | "
                    f"media_key={item.get('media_key') or '—'} | "
                    f"error={item.get('error') or '—'}"
                )

        settings_error = self.settings_store.last_load_error
        if settings_error:
            lines.append(f"Settings load fallback: {settings_error}")
        last_error = health.get("last_error")
        if last_error:
            lines.append(f"Last error: {last_error}")
        self._last_diagnostics_report = "\n".join(lines)
        self.settings.set_diagnostic_status(
            "System report готов — можно Copy report",
            report_available=True,
        )
        self.statusBar().showMessage("Diagnostics report готов", 3000)

    def _copy_diagnostics_report(self) -> None:
        if not self._last_diagnostics_report:
            self._run_diagnostics()
        QGuiApplication.clipboard().setText(self._last_diagnostics_report)
        self.statusBar().showMessage("Diagnostics report скопирован", 3000)

    def _database_quick_check(self) -> None:
        self.settings.set_database_check_status("Проверяю…")
        db_path = self.paths.database

        def worker() -> None:
            try:
                if not db_path.exists():
                    raise FileNotFoundError(str(db_path))
                uri = f"file:{db_path.as_posix()}?mode=ro"
                connection = sqlite3.connect(uri, uri=True, timeout=3.0)
                try:
                    rows = connection.execute("PRAGMA quick_check").fetchall()
                finally:
                    connection.close()
                values = [str(row[0]) for row in rows]
                ok = values == ["ok"]
                message = "PASS — ok" if ok else "FAILED — " + "; ".join(values[:5])
                self.bus.maintenance_done.emit({"kind": "db_check", "ok": ok, "message": message})
            except Exception as exc:
                self.bus.maintenance_done.emit({
                    "kind": "db_check",
                    "ok": False,
                    "message": f"FAILED — {type(exc).__name__}: {exc}",
                })

        threading.Thread(target=worker, name="dds-db-quick-check", daemon=True).start()

    def _path(self, key: str) -> str:
        return self.latest_snapshot.get("paths", {}).get(key) or str(getattr(self.paths, key))

    def _open(self, key: str, label: str) -> None:
        ok, detail = open_folder(self._path(key))
        if ok:
            self.statusBar().showMessage(f"{label}: {detail}", 3500)
        else:
            QMessageBox.warning(self, "DDS", detail)

    def open_dds(self) -> None:
        self._open("dds_data", "DDS_Data")

    def open_logs(self) -> None:
        self._open("logs", "Logs")

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            not self._update_install_launched
            and self.update_controller.prepared is not None
            and self.settings_store.settings.update_auto_install_enabled
        ):
            self._launch_prepared_update(close_after=False)
        self._closing = True
        self.status_text.setText("Останавливаю watcher…")
        if self.runtime is not None:
            self.runtime.stop()
        if self.runtime_thread is not None and self.runtime_thread.is_alive():
            self.runtime_thread.join(timeout=1.8)
        event.accept()
