from __future__ import annotations

import ctypes
import sqlite3
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication, QResizeEvent, QShowEvent
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
from dds_companion.core.settings import SettingsStore
from dds_companion.services.media_cache_service import MediaCacheService

from .layout_profile import choose_layout_profile
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
    maintenance_done = Signal(object)


class MainWindow(QMainWindow):
    PAGE_NAMES = ("Dashboard", "Library", "Activity", "Health", "Settings")
    PAGE_LABELS = ("Главная", "Библиотека", "Активность", "Статус", "Настройки")

    def __init__(self, *, dds_data: str | None = None, app_data: str | None = None, poll_ms: int = 750, settle_ms: int = 500):
        super().__init__()
        self.setWindowTitle(f"DDS Companion {__version__}")
        self.setMinimumSize(960, 600)
        self._layout_profile: str | None = None
        self._screen_signals_connected = False
        self._observed_screen = None
        self._startup_foreground_attempted = False

        self.bus = SignalBus()
        self.paths = build_runtime_paths(dds_data, app_data)
        self.settings_store = SettingsStore(self.paths.settings)
        self.media_cache = MediaCacheService(self.paths.media, self.paths.database)
        self._last_diagnostics_report = ""
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
                "config": str(self.paths.config),
                "settings": str(self.paths.settings),
            },
            "settings": self.settings_store.snapshot(),
        }
        self._closing = False

        self._build_ui()
        self._connect_signals()
        self._size_for_primary_screen()
        self._apply_layout_profile(force=True)
        self.runtime_thread.start()
        self._run_cache_policy_async("startup")

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
        title = QLabel("DDS")
        title.setObjectName("BrandTitle")
        title2 = QLabel("Companion")
        title2.setObjectName("BrandTitle")
        subtitle = QLabel(f"v{__version__}")
        subtitle.setObjectName("BrandSub")
        brand_text.addWidget(title)
        brand_text.addWidget(title2)
        brand_text.addWidget(subtitle)
        brand.addWidget(mark)
        brand.addLayout(brand_text, 1)
        side.addLayout(brand)
        side.addSpacing(16)

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
        self.library = LibraryPage(self.open_library)
        self.activity = ActivityPage()
        self.health = HealthPage(
            on_media_retry=self._retry_media_issue,
            on_media_ignore=self._ignore_media_issue,
        )
        self.settings = SettingsPage(
            on_setting_changed=self._on_setting_changed,
            on_clear_media_cache=self._clear_media_cache,
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

        # Qt path first: sufficient on most desktops and harmless elsewhere.
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

        if sys.platform != "win32":
            return

        # Windows fallback for the common Explorer -> batch -> pythonw launch.
        # TOPMOST is toggled only inside this one-shot startup call and removed
        # immediately; Companion is never kept Always-on-Top.
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
            # Foreground polish must never make Companion fail to start.
            pass

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_layout_profile()

    def _connect_signals(self) -> None:
        self.bus.snapshot.connect(self._on_snapshot)
        self.bus.activity.connect(self._on_activity)
        self.bus.watch_event.connect(self._on_watch_event)
        self.bus.runtime_error.connect(self._on_runtime_error)
        self.bus.stopped.connect(self._on_runtime_stopped)
        self.bus.maintenance_done.connect(self._on_maintenance_done)

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == self.PAGE_NAMES.index("Dashboard"):
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
        snapshot["settings"] = self.settings_store.snapshot()
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

    def _retry_media_issue(self, media_key: str) -> None:
        if not media_key:
            return
        self.runtime.request_media_retry(media_key)
        self.statusBar().showMessage("Повторная загрузка медиа запущена…", 3500)
        self.runtime.request_refresh()

    def _ignore_media_issue(self, media_key: str) -> None:
        if not media_key:
            return
        self.runtime.request_media_ignore(media_key)
        self.statusBar().showMessage("Проблема медиа помечена как игнорируемая", 3500)
        self.runtime.request_refresh()

    def _on_setting_changed(self, key: str, value) -> None:
        try:
            self.settings_store.update(**{key: value})
        except Exception as exc:
            QMessageBox.warning(self, "DDS Companion", f"Не удалось сохранить настройку:\n{exc}")
            return
        self.statusBar().showMessage("Настройка сохранена", 2500)
        self._refresh_settings_surface()
        if key == "media_autodownload_enabled":
            self.runtime.request_media_autodownload_change(bool(value))
        if key in {"media_cache_limit_bytes", "media_max_file_bytes", "media_retention_days"}:
            self._run_cache_policy_async("settings")

    def _refresh_settings_surface(self) -> None:
        if not self.latest_snapshot:
            return
        snapshot = dict(self.latest_snapshot)
        snapshot["settings"] = self.settings_store.snapshot()
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

    def _clear_media_cache(self) -> None:
        if int(self.latest_snapshot.get("stats", {}).get("media_bytes", 0)) <= 0:
            self.statusBar().showMessage("Media cache уже пуст", 2500)
            return
        if self.settings_store.settings.confirm_media_cache_clear:
            answer = QMessageBox.question(
                self,
                "DDS Companion — Clear media cache",
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

        if kind == "cache_clear":
            self.clear_cache_worker_active = False
            if ok:
                removed = result.get("files_removed", 0)
                bytes_removed = result.get("bytes_removed", 0)
                self.statusBar().showMessage(
                    f"Media cache очищен: {removed} файлов, {bytes_removed} bytes", 5000
                )
                self.runtime.request_media_wake()
            else:
                QMessageBox.warning(self, "DDS Companion", f"Очистка cache завершилась с ошибкой:\n{error or result}")
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

        self.runtime.request_refresh()

    def _run_diagnostics(self) -> None:
        snapshot = self.latest_snapshot or {}
        health = snapshot.get("health", {})
        stats = snapshot.get("stats", {})
        paths = snapshot.get("paths", {})
        subs = health.get("subsystems", {})
        lines = [
            "DDS Companion — System report",
            f"Companion: {snapshot.get('version', __version__)}",
            f"Overall Health: {health.get('state', 'UNKNOWN')}",
            f"Plugin: {subs.get('plugin', {}).get('state', 'UNKNOWN')}",
            f"Discord: {subs.get('discord', {}).get('state', 'UNKNOWN')}",
            f"Database: {subs.get('database', {}).get('state', 'UNKNOWN')}",
            f"DDS_Data: {subs.get('dds_data', {}).get('state', 'UNKNOWN')}",
            f"Watcher: {subs.get('watcher', {}).get('state', 'UNKNOWN')}",
            f"Media Backfill: {subs.get('media', {}).get('state', 'UNKNOWN')}",
            f"Messages: {stats.get('messages', 0)}",
            f"Media known/cached: {stats.get('known_media', 0)} / {stats.get('cached_media_files', 0)}",
            f"Media queued/downloading: {stats.get('media_queued', 0)} / {stats.get('media_downloading', 0)}",
            f"Media retry/stale/failed: {stats.get('media_retryable_failed', 0)} / {stats.get('media_stale_url', 0)} / {stats.get('media_permanent_failed', 0)}",
            f"Storage bytes: {stats.get('total_known_storage_bytes', 0)}",
            f"SQLite bytes: {stats.get('sqlite_bytes', 0)}",
            f"DDS JSON bytes: {stats.get('dds_json_bytes', 0)}",
            f"Media cache bytes: {stats.get('media_bytes', 0)}",
            f"Unresolved failures: {stats.get('failed_jobs_unresolved', 0)}",
            f"DDS_Data path: {paths.get('dds_data', '—')}",
            f"App data path: {paths.get('app_data', '—')}",
            f"Settings path: {self.paths.settings}",
        ]
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
