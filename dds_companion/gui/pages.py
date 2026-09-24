from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dds_companion.core.identity import APPLICATION_DISPLAY_NAME, resource_path

from .theme import ACCENT, BORDER, DANGER, INFO, MUTED, SUCCESS, TEXT, WARNING
from .widgets import (
    Card,
    HealthRow,
    MetricCard,
    PathRow,
    SectionHeader,
    SettingRow,
    StorageDonut,
    StorageRow,
    human_activity_event,
    human_activity_level,
    human_activity_subsystem,
    human_activity_summary,
    human_health_summary,
    human_size,
    human_storage_delta,
    local_time,
    set_state_property,
    signed_size,
    state_color,
)


class Page(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        parent: QWidget | None = None,
        *,
        scrollable: bool = False,
    ):
        super().__init__(parent)
        self._layout_profile = "standard"
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(24, 20, 24, 22)
        self.root_layout.setSpacing(18)
        header = QVBoxLayout()
        header.setSpacing(3)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PageSubtitle")
        self.subtitle_label.setWordWrap(True)
        header.addWidget(self.title_label)
        header.addWidget(self.subtitle_label)
        self.root_layout.addLayout(header)

        self.scroll_area: QScrollArea | None = None
        if scrollable:
            self.scroll_area = QScrollArea()
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll_area.setFrameShape(QFrame.NoFrame)
            body_widget = QWidget()
            body_widget.setObjectName("PageScrollContent")
            body_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.body = QVBoxLayout(body_widget)
            self.body.setContentsMargins(0, 0, 6, 4)
            self.body.setSpacing(16)
            self.scroll_area.setWidget(body_widget)
            self.root_layout.addWidget(self.scroll_area, 1)
        else:
            self.body = QVBoxLayout()
            self.body.setSpacing(16)
            self.root_layout.addLayout(self.body, 1)

    def apply_layout_profile(self, profile: str) -> None:
        self._layout_profile = profile
        if profile == "compact":
            self.root_layout.setContentsMargins(16, 13, 16, 14)
            self.root_layout.setSpacing(11)
            self.body.setSpacing(10)
        elif profile == "large":
            self.root_layout.setContentsMargins(30, 24, 30, 28)
            self.root_layout.setSpacing(20)
            self.body.setSpacing(18)
        else:
            self.root_layout.setContentsMargins(24, 20, 24, 22)
            self.root_layout.setSpacing(18)
            self.body.setSpacing(16)


class DashboardPage(Page):
    def __init__(self, parent=None):
        super().__init__(
            "Главная",
            "Состояние архива, активность и использование хранилища — без технического шума.",
            parent,
            scrollable=True,
        )
        self.latest_snapshot: dict = {}

        self.metrics_grid = QGridLayout()
        metrics = self.metrics_grid
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.storage_card = MetricCard("Общее хранилище", "—", "архив + локальные служебные данные")
        self.messages_card = MetricCard("Сообщения", "—", "накопительный архив")
        self.context_card = MetricCard("Структура", "—", "серверы · каналы · треды")
        self.media_card = MetricCard("Медиа", "—", "Найдено / Стырено")
        metrics.addWidget(self.storage_card, 0, 0)
        metrics.addWidget(self.messages_card, 0, 1)
        metrics.addWidget(self.context_card, 0, 2)
        metrics.addWidget(self.media_card, 0, 3)
        for col in range(4):
            metrics.setColumnStretch(col, 1)
        self.body.addLayout(metrics)

        self.lower_grid = QGridLayout()
        lower = self.lower_grid
        lower.setHorizontalSpacing(12)
        lower.setVerticalSpacing(12)

        self.activity_card = Card()
        activity_layout = QVBoxLayout(self.activity_card)
        activity_layout.setContentsMargins(16, 14, 16, 14)
        activity_layout.setSpacing(10)
        activity_layout.addWidget(SectionHeader("Последняя активность", "Что Companion делал последним"))
        self.current_activity = QLabel("Ожидание первого события…")
        self.current_activity.setStyleSheet(f"color:{TEXT};font-size:11pt;font-weight:650;")
        self.current_activity.setWordWrap(True)
        self.activity_meta = QLabel("—")
        self.activity_meta.setObjectName("SectionHint")
        self.activity_meta.setWordWrap(True)
        activity_layout.addWidget(self.current_activity)
        activity_layout.addWidget(self.activity_meta)
        activity_layout.addStretch(1)

        self.storage_detail = Card()
        storage_layout = QVBoxLayout(self.storage_detail)
        storage_layout.setContentsMargins(16, 14, 16, 14)
        storage_layout.setSpacing(6)
        storage_layout.addWidget(SectionHeader("Использование хранилища", "Архив отдельно, медиакэш отдельно"))
        self.storage_donut = StorageDonut()
        storage_layout.addWidget(self.storage_donut, 0, Qt.AlignHCenter)
        self.storage_rows = {
            "sqlite_bytes": StorageRow("База данных", ACCENT),
            "dds_json_bytes": StorageRow("Данные DDS", INFO),
            "media_bytes": StorageRow("Медиакэш", SUCCESS),
            "other_bytes": StorageRow("Прочее", WARNING),
            "logs_bytes": StorageRow("Логи", MUTED),
        }
        for row in self.storage_rows.values():
            storage_layout.addWidget(row)
        self.session_storage = QLabel("За сессию: —")
        self.session_storage.setObjectName("SectionHint")
        storage_layout.addWidget(self.session_storage)

        self.session_card = Card()
        session_layout = QVBoxLayout(self.session_card)
        session_layout.setContentsMargins(16, 14, 16, 14)
        session_layout.setSpacing(8)
        session_layout.addWidget(SectionHeader("Текущая сессия", "Изменения после запуска Companion"))
        self.session_messages = QLabel("+0 сообщений")
        self.session_messages.setStyleSheet(f"color:{TEXT};font-size:14pt;font-weight:750;")
        self.session_imports = QLabel("+0 импортов")
        self.session_events = QLabel("+0 событий активности")
        self.session_imports.setObjectName("SectionHint")
        self.session_events.setObjectName("SectionHint")
        session_layout.addWidget(self.session_messages)
        session_layout.addWidget(self.session_imports)
        session_layout.addWidget(self.session_events)
        session_layout.addStretch(1)

        lower.addWidget(self.activity_card, 0, 0)
        lower.addWidget(self.storage_detail, 0, 1)
        lower.addWidget(self.session_card, 1, 0, 1, 2)
        lower.setColumnStretch(0, 1)
        lower.setColumnStretch(1, 1)
        self.body.addLayout(lower, 1)

    def apply_layout_profile(self, profile: str) -> None:
        super().apply_layout_profile(profile)

        metrics = self.metrics_grid
        lower = self.lower_grid
        for widget in (self.storage_card, self.messages_card, self.context_card, self.media_card):
            metrics.removeWidget(widget)
        for widget in (self.activity_card, self.storage_detail, self.session_card):
            lower.removeWidget(widget)

        if profile == "compact":
            metric_positions = (
                (self.storage_card, 0, 0),
                (self.messages_card, 0, 1),
                (self.context_card, 1, 0),
                (self.media_card, 1, 1),
            )
            for widget, row, col in metric_positions:
                metrics.addWidget(widget, row, col)
            for col in range(4):
                metrics.setColumnStretch(col, 1 if col < 2 else 0)

            lower.addWidget(self.activity_card, 0, 0)
            lower.addWidget(self.storage_detail, 1, 0)
            lower.addWidget(self.session_card, 2, 0)
            lower.setColumnStretch(0, 1)
            lower.setColumnStretch(1, 0)
            lower.setHorizontalSpacing(0)
            lower.setVerticalSpacing(10)
        else:
            metrics.addWidget(self.storage_card, 0, 0)
            metrics.addWidget(self.messages_card, 0, 1)
            metrics.addWidget(self.context_card, 0, 2)
            metrics.addWidget(self.media_card, 0, 3)
            for col in range(4):
                metrics.setColumnStretch(col, 1)

            lower.addWidget(self.activity_card, 0, 0)
            lower.addWidget(self.storage_detail, 0, 1)
            lower.addWidget(self.session_card, 1, 0, 1, 2)
            lower.setColumnStretch(0, 1)
            lower.setColumnStretch(1, 1)
            spacing = 16 if profile == "large" else 12
            lower.setHorizontalSpacing(spacing)
            lower.setVerticalSpacing(spacing)

    @staticmethod
    def _set_checkbox_value(checkbox: QCheckBox, value: bool) -> None:
        checkbox.blockSignals(True)
        try:
            checkbox.setChecked(bool(value))
        finally:
            checkbox.blockSignals(False)

    def update_snapshot(self, snapshot: dict) -> None:
        self.latest_snapshot = snapshot
        stats = snapshot.get("stats", {})
        health = snapshot.get("health", {})
        activity = snapshot.get("activity", [])

        self.storage_card.set_data(
            human_size(stats.get("total_known_storage_bytes", 0)),
            human_storage_delta(stats.get("session_storage_delta_bytes", 0), sentence_case=False),
        )
        self.messages_card.set_data(
            f"{int(stats.get('messages', 0)):,}".replace(",", " "),
            f"+{stats.get('session_messages_added', 0)} за сессию",
        )
        self.context_card.set_data(
            f"{stats.get('guilds', 0)} · {stats.get('channels', 0)} · {stats.get('threads', 0)}",
            "серверы · каналы · треды",
        )
        self.media_card.set_data(
            f"{stats.get('cached_media_files', 0)} кэшировано",
            (
                f"Известно {stats.get('known_media', 0)} из {stats.get('total_media', 0)}"
                f" · внимание {stats.get('media_attention', 0)}"
                f" · ждут ссылки {stats.get('media_unresolved', 0)}"
            ),
        )

        total = max(1, int(stats.get("total_known_storage_bytes", 0)))
        for key, row in self.storage_rows.items():
            value = int(stats.get(key, 0))
            row.set_value(value, total)
            if key in {"other_bytes", "logs_bytes"}:
                row.setVisible(value > 0)

        self.storage_donut.set_segments([
            ("База данных", int(stats.get("sqlite_bytes", 0)), ACCENT),
            ("Данные DDS", int(stats.get("dds_json_bytes", 0)), INFO),
            ("Медиакэш", int(stats.get("media_bytes", 0)), SUCCESS),
            ("Прочее", int(stats.get("other_bytes", 0)), WARNING),
            ("Логи", int(stats.get("logs_bytes", 0)), MUTED),
        ])
        self.session_storage.setText(human_storage_delta(stats.get("session_storage_delta_bytes", 0)))
        self.session_messages.setText(f"+{stats.get('session_messages_added', 0)} сообщений")
        self.session_imports.setText(f"+{stats.get('session_imports_added', 0)} импортов")
        self.session_events.setText(f"+{stats.get('session_activity_events_added', 0)} событий активности")

        if activity:
            latest = activity[0]
            summary = human_activity_summary(latest)
            event_type = str(latest.get("event_type") or "")
            if event_type == "media_backfill_enabled":
                summary = "Автозагрузка медиа включена"
            elif event_type == "media_backfill_disabled":
                summary = "Автозагрузка медиа выключена"
            self.current_activity.setText(summary)
            meta = [
                local_time(latest.get("occurred_at"), seconds=True),
                human_activity_subsystem(latest.get("subsystem", "runtime")),
                human_activity_level(latest.get("level", "INFO")),
            ]
            capture = latest.get("capture_path")
            if capture:
                meta.append(Path(capture).name)
            self.activity_meta.setText("  ·  ".join(meta))
        elif health.get("last_error"):
            self.current_activity.setText("Последняя ошибка")
            self.activity_meta.setText(str(health.get("last_error")))


class LibraryPage(Page):
    """Human-facing archive browser with Discord-like message viewing.

    The tree is navigation. The right side is content, not a second inspector.
    Future Drive selection is exposed as a simple binary user choice: export or do not export.
    """

    PAGE_SIZE = 50

    def __init__(
        self,
        parent=None,
        *,
        on_messages_requested: Callable[[dict], None] | None = None,
        on_export_rule_changed: Callable[[str, str, str], None] | None = None,
        on_scope_action: Callable[[str, dict], None] | None = None,
    ):
        super().__init__(
            "Библиотека",
            "Просмотр накопленного архива по серверам, каналам и темам.",
            parent,
        )
        self.on_messages_requested = on_messages_requested
        self.on_export_rule_changed = on_export_rule_changed
        self.on_scope_action = on_scope_action

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        tree_card = Card()
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(8)
        tree_layout.addWidget(SectionHeader("Архив", "Сервер → канал → тема"))

        self.tree = QTreeWidget()
        self.tree.setObjectName("LibraryTree")
        self.tree.setHeaderLabels(["Раздел", "Сообщений", "Медиа: известно / всего", "Выгрузка"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        # The archive tree is a click target, not a hover-driven menu.  Native
        # QTreeWidget selection/current-state painting can follow the mouse on
        # Windows when rows contain embedded combo widgets, even though no content
        # navigation signal is emitted.  Disable native selection entirely and
        # paint only the last explicitly clicked row ourselves.
        # Keep the geometry stable and never let a stale horizontal scroll offset
        # make the first column look selected/cropped when the pointer returns.
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Interactive)
        self.tree.header().resizeSection(2, 225)
        self.tree.header().setSectionResizeMode(3, QHeaderView.Fixed)
        self.tree.header().resizeSection(3, 150)
        # Content navigation must be click-driven.  Binding the preview to
        # currentItemChanged made the right-hand pane follow transient Qt
        # "current index" changes while the pointer moved across embedded
        # widgets.  Keep hover/current/selection presentation separate from the
        # explicit user action that opens a channel/thread.
        self.tree.itemClicked.connect(self._item_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        tree_layout.addWidget(self.tree, 1)

        content_card = Card()
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(10)

        self.content_title = QLabel("Выберите канал или тему")
        self.content_title.setObjectName("SectionTitle")
        self.content_hint = QLabel("Сообщения выбранного раздела появятся здесь.")
        self.content_hint.setObjectName("SectionHint")
        self.content_hint.setWordWrap(True)
        content_layout.addWidget(self.content_title)
        content_layout.addWidget(self.content_hint)

        self.show_more_button = QPushButton("Показать ещё")
        self.show_more_button.setProperty("secondary", True)
        self.show_more_button.setVisible(False)
        self.show_more_button.clicked.connect(self._request_more)
        content_layout.addWidget(self.show_more_button, 0, Qt.AlignLeft)

        self.message_scroll = QScrollArea()
        self.message_scroll.setWidgetResizable(True)
        self.message_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.message_scroll.setFrameShape(QFrame.NoFrame)
        self.message_host = QWidget()
        self.message_layout = QVBoxLayout(self.message_host)
        self.message_layout.setContentsMargins(0, 0, 6, 0)
        self.message_layout.setSpacing(8)
        self.message_empty = QLabel("Выберите канал или тему слева.")
        self.message_empty.setObjectName("SectionHint")
        self.message_empty.setWordWrap(True)
        self.message_layout.addWidget(self.message_empty)
        self.message_layout.addStretch(1)
        self.message_scroll.setWidget(self.message_host)
        content_layout.addWidget(self.message_scroll, 1)

        self.splitter.addWidget(tree_card)
        self.splitter.addWidget(content_card)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setSizes([620, 900])
        self.body.addWidget(self.splitter, 1)

        self._library: list[dict] = []
        self._media_root = Path()
        self._selected_detail: dict | None = None
        self._messages: list[dict] = []
        self._has_more = False
        self._oldest_timestamp: str | None = None
        self._oldest_id: str | None = None
        self._generation = 0
        self._message_loading = False
        self._selected_key: str | None = None

    def update_snapshot(self, snapshot: dict) -> None:
        media_root = snapshot.get("paths", {}).get("media")
        if media_root:
            self._media_root = Path(media_root)
        library = snapshot.get("library", [])
        if library == self._library:
            return
        self._library = library
        self.rebuild()

    def rebuild(self) -> None:
        expanded_ids: set[str] = set()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._collect_expanded(root.child(i), expanded_ids)
        selected_key = self._selected_key
        tree_scroll = self.tree.verticalScrollBar().value()

        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        self.tree.clear()
        selected_item = None
        for guild in self._library:
            guild_detail = self._detail("guild", guild)
            g = self._tree_item(guild["name"], guild, guild_detail, bold=True)
            self.tree.addTopLevelItem(g)
            self._install_rule_combo(g, guild_detail)

            for channel in guild.get("channels", []):
                channel_detail = self._detail("channel", channel)
                c = self._tree_item(f"# {channel['name']}", channel, channel_detail)
                c.setForeground(0, QColor("#cdd5e7"))
                g.addChild(c)
                self._install_rule_combo(c, channel_detail)

                for thread in channel.get("threads", []):
                    thread_detail = self._detail("thread", thread)
                    t = self._tree_item(f"↳ {thread['name']}", thread, thread_detail)
                    t.setForeground(0, QColor(MUTED))
                    c.addChild(t)
                    self._install_rule_combo(t, thread_detail)
                    if t.data(0, Qt.UserRole) == selected_key:
                        selected_item = t
                if c.data(0, Qt.UserRole) == selected_key:
                    selected_item = c
            if g.data(0, Qt.UserRole) == selected_key:
                selected_item = g

        for i in range(self.tree.topLevelItemCount()):
            self._restore_expanded(self.tree.topLevelItem(i), expanded_ids)

        if selected_item is None and selected_key is not None:
            selected_item = self._find_item(selected_key)
        if selected_item is not None:
            self._paint_explicit_selection(selected_item)
            detail = selected_item.data(0, Qt.UserRole + 1)
            if isinstance(detail, dict):
                self._selected_detail = detail
                self._update_content_heading(detail)
        elif selected_key is not None:
            self._selected_key = None
            self._selected_detail = None
            self._generation += 1
            self._messages = []
            self._has_more = False
            self._oldest_timestamp = None
            self._oldest_id = None
            self.show_more_button.setVisible(False)
            self._show_empty_messages("Выбранный раздел больше не существует в архиве.")
        elif not self.tree.topLevelItemCount():
            self._show_empty_messages("Архив пока пуст.")
        else:
            self._paint_explicit_selection(None)
            self._show_empty_messages("Выберите канал или тему слева.")
        self.tree.blockSignals(False)
        self.tree.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda value=tree_scroll: self.tree.verticalScrollBar().setValue(
            min(value, self.tree.verticalScrollBar().maximum())
        ))

    @staticmethod
    def _detail(kind: str, data: dict) -> dict:
        return {
            "kind": kind,
            "id": str(data.get("id") or ""),
            "name": str(data.get("name") or "Без названия"),
            "channel_type": data.get("type"),
            "message_count": int(data.get("message_count", 0)),
            "direct_message_count": int(data.get("direct_message_count", data.get("message_count", 0))),
            "thread_count": len(data.get("threads", [])),
            "media_count": int(data.get("media_count", 0)),
            "media_known": int(data.get("media_known", 0)),
            "media_cached": int(data.get("media_cached", 0)),
            "media_attention": int(data.get("media_attention", 0)),
            "media_ignored": int(data.get("media_ignored", 0)),
            "media_unresolved": int(data.get("media_unresolved", 0)),
            "export_rule": str(data.get("export_rule") or "DEFAULT"),
            "default_export_rule": str(data.get("default_export_rule") or "EXCLUDE"),
            "effective_export_rule": str(data.get("effective_export_rule") or "EXCLUDE"),
        }

    @staticmethod
    def _media_cell_text(data: dict) -> str:
        total = int(data.get("media_count", 0) or 0)
        known = int(data.get("media_known", 0) or 0)
        cached = int(data.get("media_cached", 0) or 0)
        attention = int(data.get("media_attention", 0) or 0)
        unresolved = int(data.get("media_unresolved", 0) or 0)
        ignored = int(data.get("media_ignored", 0) or 0)
        parts = [f"{known}/{total} изв.", f"{cached} кэш"]
        if attention:
            parts.append(f"{attention} внимание")
        if ignored:
            parts.append(f"{ignored} обработано")
        if unresolved:
            parts.append(f"{unresolved} ждёт")
        return " · ".join(parts)

    @staticmethod
    def _media_tooltip(data: dict) -> str:
        return (
            f"Всего вложений: {int(data.get('media_count', 0) or 0)}\n"
            f"Известно сейчас: {int(data.get('media_known', 0) or 0)}\n"
            f"Кэшировано: {int(data.get('media_cached', 0) or 0)}\n"
            f"Требует внимания: {int(data.get('media_attention', 0) or 0)}\n"
            f"Обработано: {int(data.get('media_ignored', 0) or 0)}\n"
            f"Ждёт переобнаружения: {int(data.get('media_unresolved', 0) or 0)}"
        )

    def _tree_item(self, label: str, data: dict, detail: dict, *, bold: bool = False) -> QTreeWidgetItem:
        prefix = {"guild": "g", "channel": "c", "thread": "t"}[detail["kind"]]
        media_text = self._media_cell_text(data)
        item = QTreeWidgetItem([
            label,
            str(data.get("message_count", 0)),
            media_text,
            "",
        ])
        item.setToolTip(2, self._media_tooltip(data))
        item.setData(0, Qt.UserRole, f"{prefix}:{detail['id']}")
        item.setData(0, Qt.UserRole + 1, detail)
        item.setForeground(0, QColor(TEXT))
        if bold:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        return item

    def _install_rule_combo(self, item: QTreeWidgetItem, detail: dict) -> None:
        combo = QComboBox()
        combo.setMinimumWidth(118)
        combo.setMinimumHeight(32)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.addItem("Не выгружать", "EXCLUDE")
        combo.addItem("Выгружать", "INCLUDE")
        # Older databases can still contain the internal DEFAULT/inheritance
        # representation.  The user-facing control is intentionally binary: an
        # inherited value is displayed as its already-resolved effective state.
        stored = str(detail.get("export_rule") or "DEFAULT").upper()
        wanted = stored if stored in {"INCLUDE", "EXCLUDE"} else str(
            detail.get("effective_export_rule") or "EXCLUDE"
        ).upper()
        index = combo.findData(wanted)
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)
        combo.currentIndexChanged.connect(
            lambda _index, c=combo, d=detail: self._rule_changed(c, d)
        )
        item.setSizeHint(3, combo.sizeHint())
        self.tree.setItemWidget(item, 3, combo)

    def _rule_changed(self, combo: QComboBox, detail: dict) -> None:
        mode = str(combo.currentData() or "EXCLUDE")
        detail["export_rule"] = mode
        if self.on_export_rule_changed is not None:
            self.on_export_rule_changed(detail["kind"], detail["id"], mode)

    def _paint_explicit_selection(self, selected: QTreeWidgetItem | None) -> None:
        selected_brush = QBrush(QColor("#242b40"))
        clear_brush = QBrush()

        def walk(item: QTreeWidgetItem) -> None:
            brush = selected_brush if item is selected else clear_brush
            # The fourth column is occupied by a real QComboBox widget.  Paint the
            # data columns only; this gives a stable explicit-click marker without
            # fighting the embedded control's own palette.
            for column in range(3):
                item.setBackground(column, brush)
            for child_index in range(item.childCount()):
                walk(item.child(child_index))

        root = self.tree.invisibleRootItem()
        for top_index in range(root.childCount()):
            walk(root.child(top_index))

    def _item_clicked(self, current: QTreeWidgetItem, column: int) -> None:
        del column
        detail = current.data(0, Qt.UserRole + 1)
        if not isinstance(detail, dict):
            return
        self._selected_key = str(current.data(0, Qt.UserRole) or "") or None
        self._paint_explicit_selection(current)
        self._selected_detail = detail
        self._generation += 1
        self._messages = []
        self._has_more = False
        self._oldest_timestamp = None
        self._oldest_id = None
        # A request for the previously selected node may still be in flight.
        # Selection generations already make stale responses safe to discard, so
        # the new explicit click must be allowed to queue its own request instead
        # of inheriting the previous node's loading lock.
        self._message_loading = False
        self.show_more_button.setVisible(False)

        self._update_content_heading(detail)

        if detail.get("kind") == "guild":
            self._show_empty_messages("Сообщения сервера не смешиваются в одну ленту.")
            return
        self._request_messages(reset=True)

    def _show_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        detail = item.data(0, Qt.UserRole + 1)
        if not isinstance(detail, dict):
            return
        self._selected_key = str(item.data(0, Qt.UserRole) or "") or None
        self._paint_explicit_selection(item)
        self._selected_detail = detail
        self._update_content_heading(detail)

        menu = QMenu(self.tree)
        package = menu.addMenu("Упаковать")
        text_only = package.addAction("Только текст")
        text_cache = package.addAction("Текст + кэш")
        menu.addSeparator()
        clear_cache = menu.addAction("Очистить медиакэш этой ветки")
        delete_data = menu.addAction("Удалить данные ветки")
        delete_branch = menu.addAction("Полностью удалить ветку")

        chosen = menu.exec(self.tree.viewport().mapToGlobal(position))
        if chosen is None or self.on_scope_action is None:
            return
        action = None
        if chosen is text_only:
            action = "package_text"
        elif chosen is text_cache:
            action = "package_text_cache"
        elif chosen is clear_cache:
            action = "clear_branch_media"
        elif chosen is delete_data:
            action = "delete_branch_data"
        elif chosen is delete_branch:
            action = "delete_branch"
        if action:
            self.on_scope_action(action, dict(detail))

    def _update_content_heading(self, detail: dict) -> None:
        if detail.get("kind") == "guild":
            self.content_title.setText(detail.get("name") or "Сервер")
            self.content_hint.setText("Выберите канал или тему этого сервера.")
            return
        title = detail.get("name") or "Без названия"
        if detail.get("kind") == "channel":
            title = f"# {title}"
        self.content_title.setText(title)
        media = (
            f"медиа: {detail.get('media_known', 0)}/{detail.get('media_count', 0)} известно"
            f" · {detail.get('media_cached', 0)} кэш"
        )
        if int(detail.get("media_attention", 0)):
            media += f" · {detail.get('media_attention', 0)} требуют внимания"
        if int(detail.get("media_unresolved", 0)):
            media += f" · {detail.get('media_unresolved', 0)} ждут ссылку"
        if detail.get("kind") == "channel":
            direct = int(detail.get("direct_message_count", 0))
            total = int(detail.get("message_count", 0))
            if total != direct:
                self.content_hint.setText(f"{direct} сообщений в канале · {total} всего с темами · {media}")
            else:
                self.content_hint.setText(f"{direct} сообщений · {media}")
        else:
            self.content_hint.setText(f"{detail.get('message_count', 0)} сообщений · {media}")

    def _request_messages(self, *, reset: bool) -> None:
        detail = self._selected_detail
        if detail is None or detail.get("kind") not in {"channel", "thread"}:
            return
        if self._message_loading or self.on_messages_requested is None:
            return
        self._message_loading = True
        self.show_more_button.setEnabled(False)
        if reset:
            self._show_empty_messages("Загружаю сообщения…")
        self.on_messages_requested({
            "scope_kind": detail["kind"],
            "scope_id": detail["id"],
            "limit": self.PAGE_SIZE,
            "before_timestamp": None if reset else self._oldest_timestamp,
            "before_id": None if reset else self._oldest_id,
            "generation": self._generation,
            "reset": reset,
        })

    def _request_more(self) -> None:
        if self._has_more:
            self._request_messages(reset=False)

    def set_message_page(self, payload: dict) -> None:
        detail = self._selected_detail
        if detail is None:
            return
        if payload.get("generation") != self._generation:
            return
        if payload.get("scope_kind") != detail.get("kind") or payload.get("scope_id") != detail.get("id"):
            return
        self._message_loading = False
        self.show_more_button.setEnabled(True)
        error = payload.get("error")
        if error:
            self._show_empty_messages(f"Не удалось загрузить сообщения: {error}")
            self.show_more_button.setVisible(False)
            return

        incoming = list(payload.get("messages") or [])
        if payload.get("reset"):
            self._messages = incoming
        else:
            known = {str(item.get("id")) for item in self._messages}
            older = [item for item in incoming if str(item.get("id")) not in known]
            self._messages = older + self._messages
        self._has_more = bool(payload.get("has_more"))
        if self._messages:
            self._oldest_timestamp = self._messages[0].get("sort_time")
            self._oldest_id = self._messages[0].get("id")
        self.show_more_button.setVisible(self._has_more)
        self._render_messages()

    def _render_messages(self) -> None:
        self._clear_message_layout()
        if not self._messages:
            detail = self._selected_detail or {}
            if (
                detail.get("kind") == "channel"
                and int(detail.get("direct_message_count", 0)) == 0
                and int(detail.get("thread_count", 0)) > 0
            ):
                empty_text = "В самом канале сообщений нет. Выберите тему слева — сообщения находятся внутри неё."
            else:
                empty_text = "В этом разделе пока нет сохранённых сообщений."
            self.message_empty = QLabel(empty_text)
            self.message_empty.setObjectName("SectionHint")
            self.message_layout.addWidget(self.message_empty)
            self.message_layout.addStretch(1)
            return
        for message in self._messages:
            self.message_layout.addWidget(self._message_card(message))
        self.message_layout.addStretch(1)

    @staticmethod
    def _discord_markdown(content: str) -> str:
        """Normalize Discord-only tokens before Qt Markdown renders the text.

        Qt has no knowledge of Discord custom emoji tags such as
        ``<:name:123>`` / ``<a:name:123>`` and can present them as an empty
        object/glyph.  Keep the message readable without pretending that the
        unavailable remote emoji image was cached locally.
        """
        value = re.sub(r"<a?:([A-Za-z0-9_]+):\d+>", r":\1:", str(content or ""))
        return value.replace("\uFFFC", "•")

    def _message_card(self, message: dict) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        author = QLabel(str(message.get("author_name") or "Неизвестный автор"))
        author.setStyleSheet(f"color:{TEXT};font-weight:750;")
        when = QLabel(local_time(message.get("timestamp"), seconds=True))
        when.setObjectName("SectionHint")
        header.addWidget(author)
        header.addStretch(1)
        header.addWidget(when)
        layout.addLayout(header)

        content = str(message.get("content") or "").strip()
        if content:
            text = QLabel()
            text.setTextFormat(Qt.MarkdownText)
            text.setText(self._discord_markdown(content))
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
            text.setStyleSheet(f"color:{TEXT};")
            layout.addWidget(text)

        for attachment in message.get("attachments") or []:
            layout.addWidget(self._attachment_widget(attachment))
        for embed in message.get("embeds") or []:
            layout.addWidget(self._embed_widget(embed))
        if not content and not message.get("attachments") and not message.get("embeds"):
            empty = QLabel("Сообщение без текстового содержимого")
            empty.setObjectName("SectionHint")
            layout.addWidget(empty)
        return card

    def _attachment_widget(self, attachment: dict) -> QWidget:
        box = QFrame()
        box.setProperty("card", True)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        name = QLabel(str(attachment.get("filename") or "Вложение"))
        name.setStyleSheet(f"color:{TEXT};font-weight:650;")
        layout.addWidget(name)

        details = []
        content_type = attachment.get("content_type")
        if content_type:
            details.append(str(content_type))
        size = attachment.get("size")
        if size is not None:
            details.append(human_size(int(size)))
        state = str(attachment.get("media_state") or "KNOWN")
        details.append("сохранено локально" if state == "CACHED" else "не сохранено локально")
        meta = QLabel(" · ".join(details))
        meta.setObjectName("SectionHint")
        layout.addWidget(meta)

        description = str(attachment.get("description") or "").strip()
        if description:
            desc = QLabel(description)
            desc.setObjectName("SectionHint")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        relpath = attachment.get("local_relpath")
        if relpath and str(content_type or "").lower().startswith("image/"):
            path = self._media_root / str(relpath)
            if path.is_file():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    preview = QLabel()
                    preview.setAlignment(Qt.AlignLeft)
                    preview.setPixmap(
                        pixmap.scaled(560, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    layout.addWidget(preview)
        return box

    @staticmethod
    def _embed_widget(embed: dict) -> QWidget:
        box = QFrame()
        box.setProperty("card", True)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        title = QLabel(str(embed.get("title") or "Встроенное вложение"))
        title.setStyleSheet(f"color:{TEXT};font-weight:650;")
        layout.addWidget(title)
        description = str(embed.get("description") or "").strip()
        if description:
            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(desc)
        return box

    def _show_empty_messages(self, text: str) -> None:
        self._clear_message_layout()
        self.message_empty = QLabel(text)
        self.message_empty.setObjectName("SectionHint")
        self.message_empty.setWordWrap(True)
        self.message_layout.addWidget(self.message_empty)
        self.message_layout.addStretch(1)

    def _clear_message_layout(self) -> None:
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _collect_expanded(self, item: QTreeWidgetItem, ids: set[str]) -> None:
        if item.isExpanded():
            ids.add(item.data(0, Qt.UserRole))
        for i in range(item.childCount()):
            self._collect_expanded(item.child(i), ids)

    def _restore_expanded(self, item: QTreeWidgetItem, ids: set[str]) -> None:
        if item.data(0, Qt.UserRole) in ids:
            item.setExpanded(True)
        for i in range(item.childCount()):
            self._restore_expanded(item.child(i), ids)

    def _find_item(self, key: str) -> QTreeWidgetItem | None:
        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, Qt.UserRole) == key:
                return item
            for index in range(item.childCount()):
                found = walk(item.child(index))
                if found is not None:
                    return found
            return None

        for index in range(self.tree.topLevelItemCount()):
            found = walk(self.tree.topLevelItem(index))
            if found is not None:
                return found
        return None


class ActivityPage(Page):
    def __init__(self, parent=None):
        super().__init__(
            "Активность",
            "Человеческий журнал действий Companion без файлового спама и технической каши.",
            parent,
        )
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Время", "Уровень", "Подсистема", "Событие", "Описание"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 225)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.body.addWidget(card, 1)
        self._fingerprint = None

    @staticmethod
    def _presentation_events(events: list[dict]) -> list[dict]:
        visible: list[dict] = []
        last_health_signature = None
        for event in events:
            if str(event.get("event_type") or "") == "health_reason_changed":
                details = event.get("details") if isinstance(event.get("details"), dict) else {}
                state = str(details.get("state") or "UNKNOWN")
                signature = tuple(
                    (str(item.get("subsystem") or ""), str(item.get("code") or ""), state)
                    for item in (details.get("reasons") or [])
                )
                if signature and signature == last_health_signature:
                    continue
                last_health_signature = signature
            else:
                last_health_signature = None
            visible.append(event)
        return visible

    def update_snapshot(self, snapshot: dict) -> None:
        events = self._presentation_events(list(snapshot.get("activity", [])))
        fingerprint = tuple((e.get("id"), e.get("occurred_at"), e.get("summary")) for e in events)
        if fingerprint == self._fingerprint:
            return
        self._fingerprint = fingerprint
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [
                local_time(event.get("occurred_at"), seconds=True),
                human_activity_level(event.get("level", "INFO")),
                human_activity_subsystem(event.get("subsystem", "—")),
                human_activity_event(event.get("event_type", "—")),
                human_activity_summary(event),
            ]
            color = {
                "ERROR": DANGER,
                "WARNING": WARNING,
                "INFO": MUTED,
            }.get(event.get("level", "INFO").upper(), MUTED)
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 1:
                    item.setForeground(QColor(color))
                elif col == 4:
                    item.setForeground(QColor(TEXT))
                else:
                    item.setForeground(QColor("#aab3c4"))
                if col == 3:
                    item.setToolTip(f"Техническое событие: {event.get('event_type', '—')}")
                elif col == 4:
                    item.setToolTip(str(event.get("summary") or value))
                else:
                    item.setToolTip(str(value))
                self.table.setItem(row, col, item)


class HealthPage(Page):
    def __init__(
        self,
        on_media_retry=None,
        on_media_ignore=None,
        on_media_ignore_all=None,
        on_media_clear_processed=None,
        parent=None,
    ):
        super().__init__(
            "Статус",
            "Состояние подсистем и жизненный цикл медиа — раздельно и без смешивания технических сигналов.",
            parent,
            scrollable=False,
        )
        self.on_media_retry = on_media_retry
        self.on_media_ignore = on_media_ignore
        self.on_media_ignore_all = on_media_ignore_all
        self.on_media_clear_processed = on_media_clear_processed
        self._media_issue_by_key: dict[str, dict] = {}
        self._media_attention_count = 0
        self._media_ignored_count = 0
        self._media_issue_fingerprint: tuple = ()

        self.tabs = QTabWidget()
        self.tabs.setObjectName("HealthTabs")
        self.body.addWidget(self.tabs, 1)

        status, status_layout = self._make_scroll_tab()
        lifecycle, lifecycle_layout = self._make_scroll_tab()
        self.tabs.addTab(status, "Статус")
        self.tabs.addTab(lifecycle, "Жизненный цикл медиа")

        self.overall = Card()
        o = QHBoxLayout(self.overall)
        o.setContentsMargins(18, 16, 18, 16)
        texts = QVBoxLayout()
        title = QLabel("Общее состояние")
        title.setObjectName("SectionTitle")
        self.overall_hint = QLabel("Ожидание данных…")
        self.overall_hint.setObjectName("SectionHint")
        texts.addWidget(title)
        texts.addWidget(self.overall_hint)
        self.overall_pill = QLabel("STARTING")
        self.overall_pill.setObjectName("StatusPill")
        set_state_property(self.overall_pill, "STARTING")
        o.addLayout(texts, 1)
        o.addWidget(self.overall_pill)
        status_layout.addWidget(self.overall)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards: dict[str, tuple[Card, QLabel, QLabel, QLabel]] = {}
        names = [
            ("database", "База данных"),
            ("dds_data", "DDS_Data"),
            ("importer", "Импорт"),
            ("watcher", "Наблюдение"),
            ("discord", "Discord"),
            ("plugin", "DDS Plugin"),
            ("media", "Загрузка медиа"),
            ("updates", "Обновления"),
        ]
        for index, (key, label) in enumerate(names):
            card = Card()
            lay = QVBoxLayout(card)
            lay.setContentsMargins(16, 14, 16, 14)
            lay.setSpacing(7)
            top = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName("SectionTitle")
            state = QLabel("UNKNOWN")
            state.setStyleSheet(f"color:{MUTED};font-weight:750;")
            top.addWidget(name)
            top.addStretch(1)
            top.addWidget(state)
            summary = QLabel("—")
            summary.setObjectName("SectionHint")
            summary.setWordWrap(True)
            updated = QLabel("Обновлено: —")
            updated.setObjectName("SectionHint")
            updated.setWordWrap(True)
            lay.addLayout(top)
            lay.addWidget(summary)
            lay.addWidget(updated)
            lay.addStretch(1)
            grid.addWidget(card, index // 2, index % 2)
            self.cards[key] = (card, state, summary, updated)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        status_layout.addLayout(grid)

        err = Card()
        err_layout = QVBoxLayout(err)
        err_layout.setContentsMargins(16, 14, 16, 14)
        err_layout.addWidget(SectionHeader(
            "Последняя критическая ошибка",
            "Проблемы отдельных медиафайлов находятся на вкладке «Жизненный цикл медиа».",
        ))
        self.last_error = QLabel("Критических ошибок нет")
        self.last_error.setWordWrap(True)
        self.last_error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.last_error.setStyleSheet(f"color:{MUTED};")
        err_layout.addWidget(self.last_error)
        status_layout.addWidget(err)
        status_layout.addStretch(1)

        lifecycle_layout.addWidget(SectionHeader(
            "Жизненный цикл медиа",
            "Discord-ссылки не вечные: здесь видно, что известно сейчас, что уже закэшировано и что ждёт новой ссылки.",
        ))
        lifecycle_metrics = QGridLayout()
        lifecycle_metrics.setHorizontalSpacing(12)
        lifecycle_metrics.setVerticalSpacing(12)
        self.media_total_card = MetricCard("Всего вложений", "—", "стабильные записи архива")
        self.media_known_card = MetricCard("Известно", "—", "есть рабочая ссылка или локальная копия")
        self.media_cached_card = MetricCard("Кэшировано", "—", "файл сохранён локально")
        self.media_attention_card = MetricCard("Требует внимания", "—", "ошибка или протухшая ссылка")
        self.media_ignored_card = MetricCard("Обработано", "—", "игнорируется до очистки")
        self.media_unresolved_card = MetricCard("Ждёт переобнаружения", "—", "нужна свежая ссылка Discord")
        lifecycle_cards = [
            self.media_total_card,
            self.media_known_card,
            self.media_cached_card,
            self.media_attention_card,
            self.media_ignored_card,
            self.media_unresolved_card,
        ]
        for i, card in enumerate(lifecycle_cards):
            lifecycle_metrics.addWidget(card, i // 3, i % 3)
        for col in range(3):
            lifecycle_metrics.setColumnStretch(col, 1)
        lifecycle_layout.addLayout(lifecycle_metrics)

        runtime_card = Card()
        runtime_layout = QVBoxLayout(runtime_card)
        runtime_layout.setContentsMargins(16, 14, 16, 14)
        runtime_layout.setSpacing(8)
        runtime_top = QHBoxLayout()
        runtime_top.addWidget(QLabel("Загрузка медиа"))
        runtime_top.addStretch(1)
        self.media_runtime_state = QLabel("UNKNOWN")
        self.media_runtime_state.setStyleSheet(f"color:{MUTED};font-weight:750;")
        runtime_top.addWidget(self.media_runtime_state)
        self.media_runtime_summary = QLabel("Ожидание данных…")
        self.media_runtime_summary.setObjectName("SectionHint")
        self.media_runtime_summary.setWordWrap(True)
        runtime_layout.addLayout(runtime_top)
        runtime_layout.addWidget(self.media_runtime_summary)
        lifecycle_layout.addWidget(runtime_card)

        self.media_attention = Card()
        media_attention_layout = QVBoxLayout(self.media_attention)
        media_attention_layout.setContentsMargins(16, 14, 16, 14)
        media_attention_layout.setSpacing(10)
        self.media_attention_header = SectionHeader(
            "Медиафайлы, требующие внимания",
            "Повтори загрузку, посмотри причину, игнорируй выборочно или обработай весь текущий список разом.",
        )
        media_attention_layout.addWidget(self.media_attention_header)
        self.media_attention_summary = QLabel("Медиа-проблем нет")
        self.media_attention_summary.setObjectName("SectionHint")
        media_attention_layout.addWidget(self.media_attention_summary)
        self.media_issue_table = QTableWidget(0, 3)
        self.media_issue_table.setHorizontalHeaderLabels(["Файл", "Причина", "Состояние"])
        self.media_issue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.media_issue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.media_issue_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.media_issue_table.setAlternatingRowColors(True)
        self.media_issue_table.verticalHeader().setVisible(False)
        self.media_issue_table.setColumnWidth(0, 280)
        self.media_issue_table.setColumnWidth(2, 170)
        self.media_issue_table.setMinimumHeight(180)
        self.media_issue_table.setMaximumHeight(360)
        self.media_issue_table.horizontalHeader().setStretchLastSection(False)
        self.media_issue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.media_issue_table.itemSelectionChanged.connect(self._update_media_action_state)
        media_attention_layout.addWidget(self.media_issue_table)

        media_actions = QHBoxLayout()
        self.media_retry_button = QPushButton("Повторить")
        self.media_ignore_button = QPushButton("Игнорировать")
        self.media_ignore_all_button = QPushButton("Игнорировать всё")
        self.media_details_button = QPushButton("Подробнее")
        self.media_clear_processed_button = QPushButton("Очистить обработанные")
        self.media_retry_button.clicked.connect(self._retry_selected_media)
        self.media_ignore_button.clicked.connect(self._ignore_selected_media)
        self.media_ignore_all_button.clicked.connect(self._ignore_all_media)
        self.media_details_button.clicked.connect(self._show_selected_media_details)
        self.media_clear_processed_button.clicked.connect(self._clear_processed_media)
        media_actions.addWidget(self.media_retry_button)
        media_actions.addWidget(self.media_ignore_button)
        media_actions.addWidget(self.media_ignore_all_button)
        media_actions.addWidget(self.media_details_button)
        media_actions.addStretch(1)
        media_actions.addWidget(self.media_clear_processed_button)
        media_attention_layout.addLayout(media_actions)
        lifecycle_layout.addWidget(self.media_attention)
        lifecycle_layout.addStretch(1)
        self._update_media_action_state()

    @staticmethod
    def _make_scroll_tab() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 6, 4)
        layout.setSpacing(16)
        scroll.setWidget(host)
        root.addWidget(scroll)
        return page, layout

    @staticmethod
    def _attention_count_text(count: int) -> str:
        count = max(0, int(count))
        mod10 = count % 10
        mod100 = count % 100
        if mod10 == 1 and mod100 != 11:
            return f"{count} медиафайл требует внимания"
        if mod10 in {2, 3, 4} and mod100 not in {12, 13, 14}:
            return f"{count} медиафайла требуют внимания"
        return f"{count} медиафайлов требуют внимания"

    @staticmethod
    def _human_media_reason(item: dict) -> str:
        failure = str(item.get("failure_class") or "")
        error = str(item.get("error") or "").strip()
        if "size mismatch" in error.lower() or failure in {"size_mismatch", "metadata_size_mismatch"}:
            return "Размер файла не совпадает с данными Discord"
        if failure == "stale_url" or item.get("state") == "STALE_URL":
            return "Ссылка Discord устарела или недоступна"
        if failure == "http_permanent":
            return "Discord вернул постоянную HTTP-ошибку"
        if error:
            return error
        return "Не удалось загрузить медиафайл"

    def _selected_media_issue(self) -> dict | None:
        row = self.media_issue_table.currentRow()
        if row < 0:
            return None
        item = self.media_issue_table.item(row, 0)
        if item is None:
            return None
        return self._media_issue_by_key.get(str(item.data(Qt.UserRole) or ""))

    def _update_media_action_state(self) -> None:
        issue = self._selected_media_issue()
        enabled = issue is not None
        ignored = bool(issue and issue.get("state") == "IGNORED")
        self.media_retry_button.setEnabled(enabled)
        self.media_ignore_button.setEnabled(enabled and not ignored)
        self.media_details_button.setEnabled(enabled)
        self.media_ignore_all_button.setEnabled(self._media_attention_count > 0)
        self.media_clear_processed_button.setEnabled(self._media_ignored_count > 0)

    def _retry_selected_media(self) -> None:
        issue = self._selected_media_issue()
        if issue and self.on_media_retry:
            self.on_media_retry(str(issue.get("media_key")))

    def _ignore_selected_media(self) -> None:
        issue = self._selected_media_issue()
        if not issue or not self.on_media_ignore:
            return
        answer = QMessageBox.question(
            self,
            "DDS — Игнорировать медиафайл",
            "Игнорировать эту проблему?\n\n"
            "Запись останется в архиве. Затем её можно либо повторить вручную, либо убрать из списка "
            "кнопкой «Очистить обработанные» и ждать свежую ссылку Discord.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.on_media_ignore(str(issue.get("media_key")))

    def _ignore_all_media(self) -> None:
        if self._media_attention_count <= 0 or not self.on_media_ignore_all:
            return
        answer = QMessageBox.question(
            self,
            "DDS — Игнорировать все проблемы",
            f"Игнорировать все текущие проблемы ({self._media_attention_count})?\n\n"
            "Они останутся как обработанные, пока ты не нажмёшь «Очистить обработанные».",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.on_media_ignore_all()

    def _clear_processed_media(self) -> None:
        if self._media_ignored_count <= 0 or not self.on_media_clear_processed:
            return
        answer = QMessageBox.question(
            self,
            "DDS — Очистить обработанные",
            f"Очистить обработанные записи ({self._media_ignored_count})?\n\n"
            "Старые ссылки будут забыты, а сами вложения останутся в архиве в состоянии "
            "«Ждёт переобнаружения». Они снова станут известными только после получения свежей ссылки Discord.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.on_media_clear_processed()

    def _show_selected_media_details(self) -> None:
        issue = self._selected_media_issue()
        if not issue:
            return
        expected = issue.get("expected_size")
        expected_text = human_size(int(expected)) if expected is not None else "неизвестно"
        text = "\n".join([
            f"Файл: {issue.get('filename') or 'без имени'}",
            f"Состояние: {issue.get('state') or 'UNKNOWN'}",
            f"Причина: {self._human_media_reason(issue)}",
            f"Ожидаемый размер: {expected_text}",
            f"Попыток: {issue.get('attempt_count', 0)}",
            f"HTTP: {issue.get('http_status') if issue.get('http_status') is not None else '—'}",
            f"Техническая причина: {issue.get('failure_class') or '—'}",
            f"Последняя ошибка: {issue.get('error') or '—'}",
            f"Media key: {issue.get('media_key') or '—'}",
        ])
        QMessageBox.information(self, "DDS — Медиафайл", text)

    def update_snapshot(self, snapshot: dict) -> None:
        health = snapshot.get("health", {})
        state = health.get("state", "UNKNOWN")
        self.overall_pill.setText(state)
        set_state_property(self.overall_pill, state)
        overall_text = {
            "RUNNING": "Все ключевые подсистемы работают штатно",
            "ERROR": "Критическая ошибка локального архива",
            "LIMITED": "Часть функций временно недоступна — подробности ниже",
        }.get(str(state).upper(), "Состояние системы обновляется")
        self.overall_hint.setText(overall_text)
        self.overall_pill.setToolTip(str(health.get("tooltip") or overall_text))
        subs = health.get("subsystems", {})
        media_info = subs.get("media", {}) or {}
        media_details = media_info.get("details", {}) or {}
        stats = snapshot.get("stats", {}) or {}

        total = int(media_details.get("total", stats.get("total_media", 0)) or 0)
        known = int(media_details.get("known", stats.get("known_media", 0)) or 0)
        cached = int(media_details.get("cached", stats.get("cached_media_files", 0)) or 0)
        attention_count = int(media_details.get("attention_count", media_details.get("attention", stats.get("media_attention", 0))) or 0)
        ignored_count = int(media_details.get("ignored", stats.get("media_ignored", 0)) or 0)
        unresolved_count = int(media_details.get("unresolved", stats.get("media_unresolved", 0)) or 0)
        queued = int(media_details.get("queued", stats.get("media_queued", 0)) or 0)
        downloading = int(media_details.get("downloading", stats.get("media_downloading", 0)) or 0)

        self._media_attention_count = attention_count
        self._media_ignored_count = ignored_count
        self.media_total_card.set_data(str(total), "все вложения, которые архив когда-либо видел")
        self.media_known_card.set_data(str(known), "доступны сейчас для работы или уже сохранены")
        self.media_cached_card.set_data(str(cached), "локальные файлы медиакэша")
        self.media_attention_card.set_data(str(attention_count), "нужна ручная проверка или решение")
        self.media_ignored_card.set_data(str(ignored_count), "осознанно обработаны пользователем")
        self.media_unresolved_card.set_data(str(unresolved_count), "ждут новой ссылки из Discord")
        media_state = str(media_info.get("state") or "UNKNOWN")
        runtime_state_text = media_state
        if unresolved_count:
            runtime_state_text += f" · переобнаружение: {unresolved_count}"
        self.media_runtime_state.setText(runtime_state_text)
        self.media_runtime_state.setStyleSheet(f"color:{state_color(media_state)};font-weight:750;")
        self.media_runtime_summary.setText(
            f"Известно: {known} из {total} · кэшировано: {cached} · очередь: {queued} · "
            f"загружается: {downloading} · внимание: {attention_count} · обработано: {ignored_count} · "
            f"ждёт переобнаружения: {unresolved_count}"
        )

        issues = list(media_details.get("attention_items") or [])
        issue_fingerprint = tuple(
            (
                str(item.get("media_key") or ""),
                str(item.get("state") or ""),
                str(item.get("failure_class") or ""),
                str(item.get("error") or ""),
                str(item.get("updated_at") or ""),
            )
            for item in issues
        )
        if issue_fingerprint != self._media_issue_fingerprint:
            selected_before = self._selected_media_issue()
            selected_key = str(selected_before.get("media_key")) if selected_before else None
            scroll_before = self.media_issue_table.verticalScrollBar().value()
            self._media_issue_by_key = {
                str(item.get("media_key")): item for item in issues if item.get("media_key")
            }
            self.media_issue_table.setUpdatesEnabled(False)
            self.media_issue_table.setRowCount(0)
            selected_row = -1
            for issue in issues:
                row = self.media_issue_table.rowCount()
                self.media_issue_table.insertRow(row)
                filename = str(issue.get("filename") or "Без имени")
                name_item = QTableWidgetItem(filename)
                name_item.setData(Qt.UserRole, str(issue.get("media_key") or ""))
                self.media_issue_table.setItem(row, 0, name_item)
                self.media_issue_table.setItem(row, 1, QTableWidgetItem(self._human_media_reason(issue)))
                state_text = "Обработано" if issue.get("state") == "IGNORED" else "Требует внимания"
                self.media_issue_table.setItem(row, 2, QTableWidgetItem(state_text))
                if selected_key and str(issue.get("media_key") or "") == selected_key:
                    selected_row = row
            if selected_row >= 0:
                self.media_issue_table.selectRow(selected_row)
            elif self.media_issue_table.rowCount() and self.media_issue_table.currentRow() < 0:
                self.media_issue_table.selectRow(0)
            self.media_issue_table.setUpdatesEnabled(True)
            self._media_issue_fingerprint = issue_fingerprint
            QTimer.singleShot(0, lambda value=scroll_before: self.media_issue_table.verticalScrollBar().setValue(
                min(value, self.media_issue_table.verticalScrollBar().maximum())
            ))
        parts = []
        if attention_count:
            parts.append(self._attention_count_text(attention_count))
        if ignored_count:
            parts.append(f"Обработано: {ignored_count}")
        if unresolved_count:
            parts.append(f"Ждёт переобнаружения: {unresolved_count}")
        self.media_attention_summary.setText(" · ".join(parts) or "Медиа-проблем нет")
        self._update_media_action_state()

        for key, (_, state_label, summary_label, updated_label) in self.cards.items():
            info = subs.get(key, {})
            sub_state = info.get("state", "UNKNOWN")
            state_label.setText(sub_state)
            state_label.setStyleSheet(f"color:{state_color(sub_state)};font-weight:750;")
            raw_summary = info.get("summary", "—")
            summary = human_health_summary(key, info)
            state_label.setToolTip(str(raw_summary))
            summary_label.setText(summary)
            if key == "discord":
                updated_label.setText(f"Проверено: {local_time(info.get('updated_at'), seconds=True)}")
            elif key == "plugin":
                details = info.get("details", {})
                version = details.get("plugin_version") or details.get("manifest_version") or "—"
                updated_label.setText(
                    f"Версия: {version}  ·  Heartbeat: {local_time(info.get('updated_at'), seconds=True)}"
                )
            elif key == "updates":
                details = info.get("details", {})
                interval = details.get("interval_hours", "—")
                attempt = local_time(details.get("last_attempt_at"), seconds=True)
                next_check = local_time(details.get("next_check_at"), seconds=True)
                updated_label.setText(
                    f"Интервал: {interval} ч  ·  Последняя попытка: {attempt}  ·  Следующая: {next_check}"
                )
            elif key == "importer":
                updated_label.setText(f"Последний импорт: {local_time(info.get('updated_at'), seconds=True)}")
            elif key == "watcher":
                updated_label.setText(f"Heartbeat: {local_time(info.get('updated_at'), seconds=True)}")
            else:
                updated_label.setText(f"Проверено: {local_time(info.get('updated_at'), seconds=True)}")
        last_error_info = health.get("last_error_info")
        if last_error_info:
            subsystem = last_error_info.get("subsystem", "unknown")
            occurred = local_time(last_error_info.get("occurred_at"), seconds=True)
            message = last_error_info.get("message", "Unknown error")
            self.last_error.setText(f"{subsystem}  ·  {occurred}\n{message}")
            self.last_error.setStyleSheet(f"color:{DANGER};")
        else:
            self.last_error.setText("Критических ошибок нет")
            self.last_error.setStyleSheet(f"color:{MUTED};")


class SettingsPage(Page):
    CACHE_LIMITS = [
        ("1 GB", 1 * 1024**3),
        ("2 GB", 2 * 1024**3),
        ("5 GB", 5 * 1024**3),
        ("10 GB", 10 * 1024**3),
        ("20 GB", 20 * 1024**3),
        ("Без ограничений", None),
    ]
    MAX_FILE_LIMITS = [
        ("25 MB", 25 * 1024**2),
        ("50 MB", 50 * 1024**2),
        ("100 MB", 100 * 1024**2),
        ("250 MB", 250 * 1024**2),
        ("500 MB", 500 * 1024**2),
        ("Без ограничений", None),
    ]
    RETENTION_LIMITS = [
        ("3 дня", 3),
        ("1 неделя", 7),
        ("1 месяц", 30),
        ("3 месяца", 90),
        ("Всегда", None),
    ]

    def __init__(
        self,
        *,
        on_setting_changed,
        on_clear_media_cache,
        on_reset_local_archive,
        on_choose_export_folder,
        on_check_updates,
        on_download_update,
        on_install_update,
        on_cancel_update,
        on_run_diagnostics,
        on_database_check,
        on_copy_report,
        parent=None,
    ):
        super().__init__(
            "Настройки",
            "Настройки и обслуживание разделены: только реальные, сохраняемые и проверяемые действия.",
            parent,
        )
        self._on_setting_changed = on_setting_changed
        self._on_choose_export_folder = on_choose_export_folder
        self._on_check_updates = on_check_updates
        self._on_download_update = on_download_update
        self._on_install_update = on_install_update
        self._on_cancel_update = on_cancel_update
        self._last_report_available = False
        self._update_release_notes = ""
        self._update_target_version = ""
        self._update_current_version = ""
        self._update_size_bytes: int | None = None

        self.tabs = QTabWidget()
        self.tabs.setObjectName("SettingsTabs")
        self.body.addWidget(self.tabs, 1)

        general, general_layout = self._make_scroll_page()
        general_layout.addWidget(SectionHeader("Общие", "Основное поведение Companion"))

        self.media_autodownload = QCheckBox("Включить")
        self.media_autodownload.toggled.connect(
            lambda value: self._on_setting_changed("media_autodownload_enabled", bool(value))
        )
        general_layout.addWidget(SettingRow(
            "Автоматическая загрузка медиа",
            "Автоматически загружать вложения Discord в локальный медиакэш.",
            control=self.media_autodownload,
        ))

        self.confirm_clear = QCheckBox("Подтверждать")
        self.confirm_clear.toggled.connect(
            lambda value: self._on_setting_changed("confirm_media_cache_clear", bool(value))
        )
        general_layout.addWidget(SettingRow(
            "Подтверждать очистку кэша",
            "Запрашивать подтверждение перед очисткой медиакэша.",
            control=self.confirm_clear,
        ))

        self.watcher_policy = QLabel("poll — · settle —")
        self.watcher_policy.setStyleSheet(f"color:{TEXT};font-weight:650;")
        general_layout.addWidget(SettingRow(
            "Политика наблюдения",
            "Технические интервалы Watcher пока доступны только для просмотра.",
            control=self.watcher_policy,
        ))
        info = QLabel(
            "Автозапуск, запуск свёрнутым, трей и поведение кнопки закрытия появятся вместе "
            "с реальной persistent-реализацией в следующих версиях."
        )
        info.setObjectName("SectionHint")
        info.setWordWrap(True)
        general_layout.addWidget(info)
        general_layout.addStretch(1)

        updates, updates_layout = self._make_scroll_page()
        updates_layout.addWidget(SectionHeader(
            "Обновления",
            "Проверка, загрузка и установка — независимые уровни автоматизации.",
        ))

        self.update_background_check = QCheckBox("Включено")
        self.update_background_check.toggled.connect(
            lambda value: self._on_setting_changed("update_background_check_enabled", bool(value))
        )
        updates_layout.addWidget(SettingRow(
            "Фоновая проверка",
            "Проверять GitHub Releases не чаще одного раза в 24 часа. Ошибка сети не влияет на работу DDS.",
            control=self.update_background_check,
        ))

        self.update_auto_download = QCheckBox("Включено")
        self.update_auto_download.toggled.connect(
            lambda value: self._on_setting_changed("update_auto_download_enabled", bool(value))
        )
        updates_layout.addWidget(SettingRow(
            "Автоматическая загрузка",
            "Если найдена новая версия, скачать её в staging и проверить SHA-256 без установки.",
            control=self.update_auto_download,
        ))

        self.update_auto_install = QCheckBox("Включено")
        self.update_auto_install.toggled.connect(
            lambda value: self._on_setting_changed("update_auto_install_enabled", bool(value))
        )
        updates_layout.addWidget(SettingRow(
            "Автоматическая установка",
            "Установить уже проверенное обновление безопасным внешним updater-процессом. Включение также включает автозагрузку.",
            control=self.update_auto_install,
        ))

        self.check_updates_button = QPushButton("Проверить обновления")
        self.check_updates_button.setProperty("secondary", True)
        self.check_updates_button.clicked.connect(self._on_check_updates)
        updates_layout.addWidget(SettingRow(
            "Ручная проверка",
            "Всегда доступна независимо от режима автоматизации.",
            control=self.check_updates_button,
        ))
        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        self.download_update_button = QPushButton("Скачать")
        self.download_update_button.setProperty("secondary", True)
        self.download_update_button.setEnabled(False)
        self.download_update_button.clicked.connect(self._on_download_update)
        self.install_update_button = QPushButton("Установить сейчас")
        self.install_update_button.setProperty("secondary", True)
        self.install_update_button.setEnabled(False)
        self.install_update_button.clicked.connect(self._on_install_update)
        self.cancel_update_button = QPushButton("Отменить")
        self.cancel_update_button.setProperty("secondary", True)
        self.cancel_update_button.setEnabled(False)
        self.cancel_update_button.clicked.connect(self._on_cancel_update)
        action_layout.addWidget(self.download_update_button)
        action_layout.addWidget(self.install_update_button)
        action_layout.addWidget(self.cancel_update_button)
        action_layout.addStretch(1)
        updates_layout.addWidget(action_row)

        self.update_status = QLabel("Обновления ещё не проверялись.")
        self.update_status.setObjectName("SettingHint")
        self.update_status.setWordWrap(True)
        updates_layout.addWidget(self.update_status)

        self.update_details = QLabel()
        self.update_details.setObjectName("SettingHint")
        self.update_details.setWordWrap(True)
        self.update_details.setVisible(False)
        updates_layout.addWidget(self.update_details)

        self.update_notes = QLabel()
        self.update_notes.setObjectName("SettingHint")
        self.update_notes.setTextFormat(Qt.PlainText)
        self.update_notes.setWordWrap(True)
        self.update_notes.setVisible(False)
        updates_layout.addWidget(self.update_notes)

        update_note = QLabel(
            "DDS никогда не заменяет работающий DDS.exe самостоятельно. "
            "Пользовательские данные не входят в update payload."
        )
        update_note.setObjectName("SectionHint")
        update_note.setWordWrap(True)
        updates_layout.addWidget(update_note)
        updates_layout.addStretch(1)

        storage, storage_layout = self._make_scroll_page()
        storage_layout.addWidget(SectionHeader(
            "Хранение медиа",
            "Сначала — политика медиакэша; архивные metadata при очистке не удаляются.",
        ))
        self.cache_limit_combo = self._combo(self.CACHE_LIMITS)
        self.max_file_combo = self._combo(self.MAX_FILE_LIMITS)
        self.retention_combo = self._combo(self.RETENTION_LIMITS)
        self.cache_limit_combo.currentIndexChanged.connect(
            lambda _i: self._emit_combo("media_cache_limit_bytes", self.cache_limit_combo)
        )
        self.max_file_combo.currentIndexChanged.connect(
            lambda _i: self._emit_combo("media_max_file_bytes", self.max_file_combo)
        )
        self.retention_combo.currentIndexChanged.connect(
            lambda _i: self._emit_combo("media_retention_days", self.retention_combo)
        )
        storage_layout.addWidget(SettingRow(
            "Лимит медиакэша",
            "При превышении удаляются самые старые медиафайлы; архивные metadata остаются.",
            control=self.cache_limit_combo,
        ))
        storage_layout.addWidget(SettingRow(
            "Максимальный размер файла",
            "Файл крупнее лимита не сохраняется в локальном медиакэше.",
            control=self.max_file_combo,
        ))
        storage_layout.addWidget(SettingRow(
            "Хранить неиспользуемые медиа",
            "Срок хранения считается по last-access/cached-at; для orphan-файлов используется безопасный fallback по mtime.",
            control=self.retention_combo,
        ))
        self.clear_media_button = QPushButton("Очистить медиакэш")
        self.clear_media_button.setProperty("secondary", True)
        self.clear_media_button.clicked.connect(on_clear_media_cache)
        storage_layout.addWidget(SettingRow(
            "Очистка медиакэша",
            "Удаляет только бинарники из media; SQLite, DDS JSON и attachment metadata не трогаются.",
            control=self.clear_media_button,
        ))

        storage_layout.addWidget(SectionHeader(
            "Ручной экспорт",
            "ZIP-пакеты создаются локально и не требуют облачной авторизации.",
        ))
        export_control = QWidget()
        export_control_layout = QHBoxLayout(export_control)
        export_control_layout.setContentsMargins(0, 0, 0, 0)
        export_control_layout.setSpacing(8)
        self.export_path_value = QLabel("—")
        self.export_path_value.setObjectName("SettingHint")
        self.export_path_value.setWordWrap(True)
        self.export_path_value.setMinimumWidth(220)
        choose_export = QPushButton("Выбрать…")
        choose_export.setProperty("secondary", True)
        choose_export.clicked.connect(self._on_choose_export_folder)
        export_control_layout.addWidget(self.export_path_value, 1)
        export_control_layout.addWidget(choose_export)
        storage_layout.addWidget(SettingRow(
            "Папка ручного экспорта",
            "Сюда DDS сохраняет ZIP из команды «Упаковать» в Библиотеке.",
            control=export_control,
        ))

        usage = Card()
        usage_layout = QVBoxLayout(usage)
        usage_layout.setContentsMargins(16, 14, 16, 14)
        usage_layout.setSpacing(6)
        usage_layout.addWidget(SectionHeader("Использование хранилища", "Источник данных и кэш считаются отдельно"))
        self.storage_total = QLabel("—")
        self.storage_total.setStyleSheet(f"color:{TEXT};font-size:17pt;font-weight:750;")
        usage_layout.addWidget(self.storage_total)
        self.storage_rows = {
            "sqlite_bytes": StorageRow("SQLite + WAL/SHM", ACCENT),
            "dds_json_bytes": StorageRow("DDS JSON", INFO),
            "media_bytes": StorageRow("Медиакэш", SUCCESS),
            "other_bytes": StorageRow("Прочее", WARNING),
            "logs_bytes": StorageRow("Логи", MUTED),
        }
        for row in self.storage_rows.values():
            usage_layout.addWidget(row)
        storage_layout.addWidget(usage)

        storage_layout.addWidget(SectionHeader(
            "Расположение файлов",
            "Редко используемый прямой доступ к папкам данных.",
        ))
        self.path_rows: dict[str, PathRow] = {}
        for key, label in [
            ("dds_data", "DDS_Data — экспорт плагина"),
            ("app_data", "Данные Companion"),
        ]:
            row = PathRow(label, "—")
            self.path_rows[key] = row
            storage_layout.addWidget(row)
        storage_layout.addStretch(1)

        archive, archive_layout = self._make_scroll_page()
        archive_layout.addWidget(SectionHeader(
            "Архив",
            "Архив можно оставить как есть или полностью начать заново; настройки DDS сохраняются.",
        ))
        self.archive_messages = QLabel("—")
        self.archive_context = QLabel("—")
        self.archive_db = QLabel("—")
        self.archive_json = QLabel("—")
        for title, hint, label in [
            ("Сообщения в архиве", "Накопительный архив сообщений", self.archive_messages),
            ("Структура архива", "Серверы · каналы · треды", self.archive_context),
            ("Размер базы", "SQLite + WAL/SHM", self.archive_db),
            ("Размер DDS JSON", "Исходные capture-файлы Plugin", self.archive_json),
        ]:
            label.setStyleSheet(f"color:{TEXT};font-weight:650;")
            archive_layout.addWidget(SettingRow(title, hint, control=label))
        self.reset_archive_button = QPushButton("Сбросить локальный архив")
        self.reset_archive_button.setProperty("danger", True)
        self.reset_archive_button.clicked.connect(on_reset_local_archive)
        archive_layout.addWidget(SettingRow(
            "Начать с чистого листа",
            "Удаляет SQLite-архив и локальный медиакэш, но сохраняет настройки DDS и исходные DDS_Data. Уже существующие capture не импортируются повторно, пока Plugin не обновит их после сброса.",
            control=self.reset_archive_button,
        ))
        archive_note = QLabel(
            "Это отдельное действие от очистки медиакэша: обычная очистка кэша сохраняет сообщения, ссылки и структуру архива."
        )
        archive_note.setObjectName("SectionHint")
        archive_note.setWordWrap(True)
        archive_layout.addWidget(archive_note)
        archive_layout.addStretch(1)

        diagnostics, diag_layout = self._make_scroll_page()
        identity_card = Card()
        identity_layout = QHBoxLayout(identity_card)
        identity_layout.setContentsMargins(16, 14, 16, 14)
        identity_layout.setSpacing(14)
        identity_logo = QLabel()
        identity_logo.setFixedSize(72, 72)
        identity_logo.setAlignment(Qt.AlignCenter)
        identity_pixmap = QPixmap(str(resource_path("assets/DDS_app_icon_master.png")))
        if not identity_pixmap.isNull():
            identity_logo.setPixmap(identity_pixmap.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        identity_text = QVBoxLayout()
        identity_text.setSpacing(3)
        identity_title = QLabel(APPLICATION_DISPLAY_NAME)
        identity_title.setStyleSheet(f"color:{TEXT};font-size:15pt;font-weight:750;")
        identity_subtitle = QLabel("Companion · локальный архив и медиаслой DDS")
        identity_subtitle.setObjectName("SectionHint")
        identity_text.addWidget(identity_title)
        identity_text.addWidget(identity_subtitle)
        identity_layout.addWidget(identity_logo)
        identity_layout.addLayout(identity_text, 1)
        diag_layout.addWidget(identity_card)
        diag_layout.addWidget(SectionHeader("Диагностика", "Логи, отчёт и безопасные проверки"))
        self.diag_rows: dict[str, PathRow] = {}
        for key, label in [
            ("logs", "Логи"),
            ("app_data", "Папка данных Companion"),
        ]:
            row = PathRow(label, "—")
            self.diag_rows[key] = row
            diag_layout.addWidget(row)

        run_diag = QPushButton("Запустить диагностику")
        run_diag.setProperty("secondary", True)
        run_diag.clicked.connect(on_run_diagnostics)
        self.diag_status = QLabel("Не запускалась")
        self.diag_status.setObjectName("SettingHint")
        diag_layout.addWidget(SettingRow(
            "Системный отчёт",
            "Снимок версий, статуса, путей, хранилища и неразрешённых ошибок.",
            control=run_diag,
        ))
        diag_layout.addWidget(self.diag_status)

        db_check = QPushButton("Быстрая проверка базы")
        db_check.setProperty("secondary", True)
        db_check.clicked.connect(on_database_check)
        self.db_check_status = QLabel("Не запускалась")
        self.db_check_status.setObjectName("SettingHint")
        diag_layout.addWidget(SettingRow(
            "Целостность SQLite",
            "PRAGMA quick_check через отдельное подключение только для чтения.",
            control=db_check,
        ))
        diag_layout.addWidget(self.db_check_status)

        self.copy_report = QPushButton("Копировать отчёт")
        self.copy_report.setProperty("secondary", True)
        self.copy_report.setEnabled(False)
        self.copy_report.clicked.connect(on_copy_report)
        diag_layout.addWidget(SettingRow(
            "Последний отчёт",
            "Копирует последний диагностический отчёт в буфер обмена.",
            control=self.copy_report,
        ))
        self.version_value = QLabel("—")
        self.plugin_value = QLabel("—")
        self.contract_value = QLabel("—")
        for title, hint, label in [
            ("Версия Companion", "Текущая версия приложения", self.version_value),
            ("Версия плагина", "Версия из heartbeat или manifest", self.plugin_value),
            ("Контракт захвата", "Версии формата захвата и heartbeat-контракта", self.contract_value),
        ]:
            label.setStyleSheet(f"color:{TEXT};font-weight:650;")
            diag_layout.addWidget(SettingRow(title, hint, control=label))
        diag_layout.addStretch(1)

        self.tabs.addTab(general, "Общие")
        self.tabs.addTab(storage, "Хранилище")
        self.tabs.addTab(archive, "Архив")
        self.tabs.addTab(updates, "Обновления")
        self.tabs.addTab(diagnostics, "Диагностика")

    @staticmethod
    def _make_scroll_page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("SettingsPathsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 4, 5, 4)
        layout.setSpacing(9)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return page, layout

    @staticmethod
    def _combo(options: list[tuple[str, object]]) -> QComboBox:
        combo = QComboBox()
        for label, value in options:
            combo.addItem(label, value)
        return combo

    def _emit_combo(self, key: str, combo: QComboBox) -> None:
        if combo.signalsBlocked():
            return
        self._on_setting_changed(key, combo.currentData())

    @staticmethod
    def _set_combo_value(combo: QComboBox, value) -> None:
        combo.blockSignals(True)
        try:
            index = next((i for i in range(combo.count()) if combo.itemData(i) == value), -1)
            if index >= 0:
                combo.setCurrentIndex(index)
        finally:
            combo.blockSignals(False)

    def update_snapshot(self, snapshot: dict) -> None:
        paths = snapshot.get("paths", {})
        for key, row in self.path_rows.items():
            row.set_path(paths.get(key, "—"))
        for key, row in self.diag_rows.items():
            row.set_path(paths.get(key, "—"))

        watcher = snapshot.get("watcher", {})
        self.watcher_policy.setText(
            f"poll={watcher.get('poll_ms', '—')} ms · settle={watcher.get('settle_ms', '—')} ms"
        )

        stats = snapshot.get("stats", {})
        total = max(1, int(stats.get("total_known_storage_bytes", 0)))
        self.storage_total.setText(human_size(stats.get("total_known_storage_bytes", 0)))
        for key, row in self.storage_rows.items():
            value = int(stats.get(key, 0))
            row.set_value(value, total)
            if key in {"other_bytes", "logs_bytes"}:
                row.setVisible(value > 0)
        self.clear_media_button.setEnabled(int(stats.get("media_bytes", 0)) > 0)
        if hasattr(self, "reset_archive_button") and self.reset_archive_button.isEnabled():
            self.reset_archive_button.setEnabled(
                int(stats.get("messages", 0)) > 0
                or int(stats.get("sqlite_bytes", 0)) > 0
                or int(stats.get("media_bytes", 0)) > 0
            )

        settings = snapshot.get("settings", {})
        self.export_path_value.setText(str(settings.get("effective_manual_export_path") or settings.get("manual_export_path") or "—"))
        self._set_combo_value(self.cache_limit_combo, settings.get("media_cache_limit_bytes"))
        self._set_combo_value(self.max_file_combo, settings.get("media_max_file_bytes"))
        self._set_combo_value(self.retention_combo, settings.get("media_retention_days"))
        self.media_autodownload.blockSignals(True)
        try:
            self.media_autodownload.setChecked(bool(settings.get("media_autodownload_enabled", False)))
        finally:
            self.media_autodownload.blockSignals(False)
        self.confirm_clear.blockSignals(True)
        try:
            self.confirm_clear.setChecked(bool(settings.get("confirm_media_cache_clear", True)))
        finally:
            self.confirm_clear.blockSignals(False)

        self._set_checkbox_value(
            self.update_background_check,
            settings.get("update_background_check_enabled", True),
        )
        self._set_checkbox_value(
            self.update_auto_download,
            settings.get("update_auto_download_enabled", False),
        )
        self._set_checkbox_value(
            self.update_auto_install,
            settings.get("update_auto_install_enabled", False),
        )

        self.archive_messages.setText(f"{int(stats.get('messages', 0)):,}".replace(",", " "))
        self.archive_context.setText(
            f"{stats.get('guilds', 0)} · {stats.get('channels', 0)} · {stats.get('threads', 0)}"
        )
        self.archive_db.setText(human_size(stats.get("sqlite_bytes", 0)))
        self.archive_json.setText(human_size(stats.get("dds_json_bytes", 0)))

        self.version_value.setText(str(snapshot.get("version", "—")))
        health = snapshot.get("health", {})
        plugin = health.get("subsystems", {}).get("plugin", {})
        details = plugin.get("details", {})
        plugin_version = details.get("plugin_version") or details.get("manifest_version") or "—"
        self.plugin_value.setText(str(plugin_version))
        capture_schema = details.get("capture_schema_version") or "—"
        heartbeat_schema = details.get("heartbeat_schema_version") or "plugin-heartbeat-v1"
        self.contract_value.setText(f"capture-v{capture_schema} · {heartbeat_schema}")

    @staticmethod
    def _format_release_notes(value: object, *, limit: int = 1400) -> str:
        raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not raw:
            return ""
        # Keep short release notes useful without letting a huge GitHub body turn
        # the Settings page into an unbounded wall of text.
        lines = [line.rstrip() for line in raw.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        text = "\n".join(lines)
        if len(text) > limit:
            text = text[: max(0, limit - 1)].rstrip() + "…"
        return text

    def set_update_status(self, payload: dict) -> None:
        state = str(payload.get("state") or "IDLE")
        message = str(payload.get("message") or state)
        self.update_status.setText(message)

        if payload.get("version"):
            self._update_target_version = str(payload.get("version"))
        if payload.get("current_version"):
            self._update_current_version = str(payload.get("current_version"))
        if payload.get("size_bytes") is not None:
            try:
                self._update_size_bytes = max(0, int(payload.get("size_bytes")))
            except (TypeError, ValueError):
                self._update_size_bytes = None
        if "notes" in payload:
            self._update_release_notes = self._format_release_notes(payload.get("notes"))
        if state == "CURRENT":
            self._update_release_notes = ""
            self._update_target_version = ""
            self._update_size_bytes = None

        details: list[str] = []
        if self._update_target_version:
            if self._update_current_version:
                details.append(f"Версия: {self._update_current_version} → {self._update_target_version}")
            else:
                details.append(f"Версия: {self._update_target_version}")
        if self._update_size_bytes:
            details.append(f"Пакет: {human_size(self._update_size_bytes)}")
        self.update_details.setText(" · ".join(details))
        self.update_details.setVisible(bool(details))

        if self._update_release_notes:
            self.update_notes.setText("Что нового:\n" + self._update_release_notes)
            self.update_notes.setVisible(True)
        else:
            self.update_notes.clear()
            self.update_notes.setVisible(False)

        busy = state in {"CHECKING", "DOWNLOADING", "VERIFYING", "CANCELLING"}
        self.check_updates_button.setEnabled(not busy)
        self.download_update_button.setEnabled(
            state == "AVAILABLE"
            or (state == "CANCELLED" and bool(self._update_target_version))
        )
        self.install_update_button.setEnabled(state == "STAGED")
        self.cancel_update_button.setEnabled(state in {"CHECKING", "DOWNLOADING", "VERIFYING"})

    def set_diagnostic_status(self, text: str, *, report_available: bool = False) -> None:
        self.diag_status.setText(text)
        self.copy_report.setEnabled(report_available)
        self._last_report_available = report_available

    def set_database_check_status(self, text: str) -> None:
        self.db_check_status.setText(text)

