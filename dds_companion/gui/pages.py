from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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
    human_size,
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
        self.media_card = MetricCard("Медиа", "—", "known / cached")
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
            "sqlite_bytes": StorageRow("SQLite + WAL/SHM", ACCENT),
            "dds_json_bytes": StorageRow("DDS JSON", INFO),
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
        self.session_imports = QLabel("+0 imports")
        self.session_events = QLabel("+0 activity events")
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

    def update_snapshot(self, snapshot: dict) -> None:
        self.latest_snapshot = snapshot
        stats = snapshot.get("stats", {})
        health = snapshot.get("health", {})
        activity = snapshot.get("activity", [])

        self.storage_card.set_data(
            human_size(stats.get("total_known_storage_bytes", 0)),
            f"за сессию {signed_size(stats.get('session_storage_delta_bytes', 0))}",
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
            f"{stats.get('known_media', 0)} / {stats.get('cached_media_files', 0)}",
            f"known / cached · embeds {stats.get('embeds', 0)}",
        )

        total = max(1, int(stats.get("total_known_storage_bytes", 0)))
        for key, row in self.storage_rows.items():
            value = int(stats.get(key, 0))
            row.set_value(value, total)
            if key in {"other_bytes", "logs_bytes"}:
                row.setVisible(value > 0)

        self.storage_donut.set_segments([
            ("SQLite", int(stats.get("sqlite_bytes", 0)), ACCENT),
            ("DDS JSON", int(stats.get("dds_json_bytes", 0)), INFO),
            ("Media cache", int(stats.get("media_bytes", 0)), SUCCESS),
            ("Other", int(stats.get("other_bytes", 0)), WARNING),
            ("Logs", int(stats.get("logs_bytes", 0)), MUTED),
        ])
        self.session_storage.setText(f"За сессию: {signed_size(stats.get('session_storage_delta_bytes', 0))}")
        self.session_messages.setText(f"+{stats.get('session_messages_added', 0)} сообщений")
        self.session_imports.setText(f"+{stats.get('session_imports_added', 0)} imports")
        self.session_events.setText(f"+{stats.get('session_activity_events_added', 0)} activity events")

        if activity:
            latest = activity[0]
            self.current_activity.setText(latest.get("summary", "—"))
            meta = [
                local_time(latest.get("occurred_at"), seconds=True),
                latest.get("subsystem", "runtime"),
                latest.get("level", "INFO"),
            ]
            capture = latest.get("capture_path")
            if capture:
                meta.append(Path(capture).name)
            self.activity_meta.setText("  ·  ".join(meta))
        elif health.get("last_error"):
            self.current_activity.setText("Последняя ошибка")
            self.activity_meta.setText(str(health.get("last_error")))


class LibraryPage(Page):
    """Human-facing archive browser.

    The tree is navigation, not a database inspector. Technical identifiers stay
    out of the main columns and are available only in the details card.
    """

    def __init__(self, parent=None):
        super().__init__(
            "Библиотека",
            "Просмотр накопленного архива по серверам, каналам и темам.",
            parent,
        )

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Поиск по серверу, каналу или теме…")
        self.filter.textChanged.connect(self.apply_filter)
        self.body.addWidget(self.filter)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        tree_card = Card()
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(10, 10, 10, 10)
        tree_layout.setSpacing(8)
        tree_layout.addWidget(SectionHeader("Архив", "Сервер → канал → тема"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Раздел", "Сообщений", "Медиа"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.currentItemChanged.connect(self._selection_changed)
        tree_layout.addWidget(self.tree, 1)

        details_card = Card()
        details_card.setMinimumWidth(285)
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(12)

        self.detail_title = QLabel("Выберите раздел")
        self.detail_title.setObjectName("SectionTitle")
        self.detail_hint = QLabel("Здесь появятся сведения о сервере, канале или теме.")
        self.detail_hint.setObjectName("SectionHint")
        self.detail_hint.setWordWrap(True)
        details_layout.addWidget(self.detail_title)
        details_layout.addWidget(self.detail_hint)

        detail_grid = QGridLayout()
        detail_grid.setHorizontalSpacing(16)
        detail_grid.setVerticalSpacing(10)
        self.detail_type = self._add_detail_row(detail_grid, 0, "Тип")
        self.detail_location = self._add_detail_row(detail_grid, 1, "Расположение")
        self.detail_messages = self._add_detail_row(detail_grid, 2, "Сообщений")
        self.detail_media = self._add_detail_row(detail_grid, 3, "Медиа")
        self.detail_activity = self._add_detail_row(detail_grid, 4, "Последняя активность")
        details_layout.addLayout(detail_grid)

        details_layout.addSpacing(4)
        technical = QLabel("Технический ID")
        technical.setObjectName("CardEyebrow")
        self.detail_id = QLabel("—")
        self.detail_id.setObjectName("SectionHint")
        self.detail_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_id.setWordWrap(True)
        details_layout.addWidget(technical)
        details_layout.addWidget(self.detail_id)

        self.copy_id_button = QPushButton("Копировать ID")
        self.copy_id_button.setProperty("secondary", True)
        self.copy_id_button.setEnabled(False)
        self.copy_id_button.clicked.connect(self.copy_selected_id)
        details_layout.addWidget(self.copy_id_button)
        details_layout.addStretch(1)

        self.splitter.addWidget(tree_card)
        self.splitter.addWidget(details_card)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([720, 360])
        self.body.addWidget(self.splitter, 1)

        self._library: list[dict] = []
        self._selected_detail: dict | None = None

    @staticmethod
    def _add_detail_row(layout: QGridLayout, row: int, label: str) -> QLabel:
        name = QLabel(label)
        name.setObjectName("CardEyebrow")
        value = QLabel("—")
        value.setStyleSheet(f"color:{TEXT};font-weight:650;")
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(name, row, 0, Qt.AlignTop)
        layout.addWidget(value, row, 1, Qt.AlignTop)
        return value

    def update_snapshot(self, snapshot: dict) -> None:
        library = snapshot.get("library", [])
        if library == self._library:
            return
        self._library = library
        self.rebuild()

    def rebuild(self) -> None:
        expanded_ids = set()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            self._collect_expanded(root.child(i), expanded_ids)
        selected_id = self.tree.currentItem().data(0, Qt.UserRole) if self.tree.currentItem() else None

        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        selected_item = None
        for guild in self._library:
            guild_detail = {
                "kind": "guild",
                "id": guild["id"],
                "name": guild["name"],
                "location": "—",
                "message_count": guild.get("message_count", 0),
                "media_count": guild.get("media_count", 0),
                "last_activity": guild.get("last_activity"),
            }
            g = QTreeWidgetItem([
                guild["name"],
                str(guild.get("message_count", 0)),
                str(guild.get("media_count", 0)),
            ])
            g.setData(0, Qt.UserRole, f"g:{guild['id']}")
            g.setData(0, Qt.UserRole + 1, guild_detail)
            g.setForeground(0, QColor(TEXT))
            font = g.font(0)
            font.setBold(True)
            g.setFont(0, font)
            self.tree.addTopLevelItem(g)

            for channel in guild.get("channels", []):
                channel_detail = {
                    "kind": "channel",
                    "id": channel["id"],
                    "name": channel["name"],
                    "channel_type": channel.get("type"),
                    "location": guild["name"],
                    "message_count": channel.get("message_count", 0),
                    "media_count": channel.get("media_count", 0),
                    "last_activity": channel.get("last_activity"),
                }
                c = QTreeWidgetItem([
                    f"# {channel['name']}",
                    str(channel.get("message_count", 0)),
                    str(channel.get("media_count", 0)),
                ])
                c.setData(0, Qt.UserRole, f"c:{channel['id']}")
                c.setData(0, Qt.UserRole + 1, channel_detail)
                c.setForeground(0, QColor("#cdd5e7"))
                g.addChild(c)

                for thread in channel.get("threads", []):
                    thread_detail = {
                        "kind": "thread",
                        "id": thread["id"],
                        "name": thread["name"],
                        "location": f"{guild['name']} → # {channel['name']}",
                        "message_count": thread.get("message_count", 0),
                        "media_count": thread.get("media_count", 0),
                        "last_activity": thread.get("last_activity"),
                    }
                    t = QTreeWidgetItem([
                        f"↳ {thread['name']}",
                        str(thread.get("message_count", 0)),
                        str(thread.get("media_count", 0)),
                    ])
                    t.setData(0, Qt.UserRole, f"t:{thread['id']}")
                    t.setData(0, Qt.UserRole + 1, thread_detail)
                    t.setForeground(0, QColor(MUTED))
                    c.addChild(t)
                    if t.data(0, Qt.UserRole) == selected_id:
                        selected_item = t
                if c.data(0, Qt.UserRole) == selected_id:
                    selected_item = c
            if g.data(0, Qt.UserRole) == selected_id:
                selected_item = g

        for i in range(self.tree.topLevelItemCount()):
            self._restore_expanded(self.tree.topLevelItem(i), expanded_ids)

        if selected_item is None and self.tree.topLevelItemCount():
            selected_item = self.tree.topLevelItem(0)
        if selected_item:
            self.tree.setCurrentItem(selected_item)
        else:
            self._show_empty_details()

        self.tree.setUpdatesEnabled(True)
        self.apply_filter(self.filter.text())

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

    def apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for i in range(self.tree.topLevelItemCount()):
            self._filter_item(self.tree.topLevelItem(i), needle)

    def _filter_item(self, item: QTreeWidgetItem, needle: str) -> bool:
        own = not needle or needle in item.text(0).casefold()
        child_match = False
        for i in range(item.childCount()):
            child_match |= self._filter_item(item.child(i), needle)
        visible = own or child_match
        item.setHidden(not visible)
        if needle and child_match:
            item.setExpanded(True)
        return visible

    def _selection_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        del previous
        if current is None:
            self._show_empty_details()
            return
        detail = current.data(0, Qt.UserRole + 1)
        if not isinstance(detail, dict):
            self._show_empty_details()
            return
        self._selected_detail = detail
        kind = detail.get("kind")
        kind_label = {
            "guild": "Сервер",
            "channel": "Форум" if detail.get("channel_type") == 15 else "Канал",
            "thread": "Тема",
        }.get(kind, "Раздел")
        title = detail.get("name") or "Без названия"
        if kind == "channel":
            title = f"# {title}"
        self.detail_title.setText(title)
        self.detail_hint.setText(f"{kind_label} в накопленном архиве DDS.")
        self.detail_type.setText(kind_label)
        self.detail_location.setText(str(detail.get("location") or "—"))
        self.detail_messages.setText(str(detail.get("message_count", 0)))
        self.detail_media.setText(str(detail.get("media_count", 0)))
        self.detail_activity.setText(local_time(detail.get("last_activity")))
        self.detail_id.setText(str(detail.get("id") or "—"))
        self.copy_id_button.setEnabled(bool(detail.get("id")))

    def _show_empty_details(self) -> None:
        self._selected_detail = None
        self.detail_title.setText("Выберите раздел")
        self.detail_hint.setText("Здесь появятся сведения о сервере, канале или теме.")
        for label in (
            self.detail_type,
            self.detail_location,
            self.detail_messages,
            self.detail_media,
            self.detail_activity,
            self.detail_id,
        ):
            label.setText("—")
        self.copy_id_button.setEnabled(False)

    def copy_selected_id(self) -> None:
        if self._selected_detail and self._selected_detail.get("id"):
            QApplication.clipboard().setText(str(self._selected_detail["id"]))


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
        self.table.setColumnWidth(3, 150)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.body.addWidget(card, 1)
        self._fingerprint = None

    def update_snapshot(self, snapshot: dict) -> None:
        events = snapshot.get("activity", [])
        fingerprint = tuple((e.get("id"), e.get("occurred_at"), e.get("summary")) for e in events)
        if fingerprint == self._fingerprint:
            return
        self._fingerprint = fingerprint
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [
                local_time(event.get("occurred_at"), seconds=True),
                event.get("level", "INFO"),
                event.get("subsystem", "—"),
                event.get("event_type", "—"),
                event.get("summary", "—"),
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
                item.setToolTip(str(value))
                self.table.setItem(row, col, item)


class HealthPage(Page):
    def __init__(self, on_media_retry=None, on_media_ignore=None, parent=None):
        super().__init__(
            "Статус",
            "Проверка жизненно важных подсистем, heartbeat и ошибок, которые не должны останавливать архив.",
            parent,
            scrollable=True,
        )
        self.on_media_retry = on_media_retry
        self.on_media_ignore = on_media_ignore
        self._media_issue_by_key: dict[str, dict] = {}

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
        self.body.addWidget(self.overall)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards: dict[str, tuple[Card, QLabel, QLabel, QLabel]] = {}
        names = [
            ("database", "Database"),
            ("dds_data", "DDS_Data"),
            ("importer", "Importer"),
            ("watcher", "Watcher"),
            ("discord", "Discord"),
            ("plugin", "DDS Plugin"),
            ("media", "Media Backfill"),
            ("updates", "Update check"),
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
        self.body.addLayout(grid)

        self.media_attention = Card()
        media_attention_layout = QVBoxLayout(self.media_attention)
        media_attention_layout.setContentsMargins(16, 14, 16, 14)
        media_attention_layout.setSpacing(10)
        self.media_attention_header = SectionHeader(
            "Медиафайлы, требующие внимания",
            "Здесь можно повторить загрузку, посмотреть причину или осознанно игнорировать проблему.",
        )
        media_attention_layout.addWidget(self.media_attention_header)
        self.media_attention_summary = QLabel("—")
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
        self.media_issue_table.setColumnWidth(2, 150)
        self.media_issue_table.setMinimumHeight(150)
        self.media_issue_table.setMaximumHeight(260)
        self.media_issue_table.horizontalHeader().setStretchLastSection(False)
        self.media_issue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.media_issue_table.itemSelectionChanged.connect(self._update_media_action_state)
        media_attention_layout.addWidget(self.media_issue_table)
        media_actions = QHBoxLayout()
        self.media_retry_button = QPushButton("Повторить")
        self.media_ignore_button = QPushButton("Игнорировать")
        self.media_details_button = QPushButton("Подробнее")
        self.media_retry_button.clicked.connect(self._retry_selected_media)
        self.media_ignore_button.clicked.connect(self._ignore_selected_media)
        self.media_details_button.clicked.connect(self._show_selected_media_details)
        media_actions.addWidget(self.media_retry_button)
        media_actions.addWidget(self.media_ignore_button)
        media_actions.addWidget(self.media_details_button)
        media_actions.addStretch(1)
        media_attention_layout.addLayout(media_actions)
        self.media_attention.setVisible(False)
        self.body.addWidget(self.media_attention)

        err = Card()
        err_layout = QVBoxLayout(err)
        err_layout.setContentsMargins(16, 14, 16, 14)
        err_layout.addWidget(SectionHeader(
            "Последняя критическая ошибка",
            "Проблемы отдельных медиафайлов отображаются отдельным блоком выше.",
        ))
        self.last_error = QLabel("Критических ошибок нет")
        self.last_error.setWordWrap(True)
        self.last_error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.last_error.setStyleSheet(f"color:{MUTED};")
        err_layout.addWidget(self.last_error)
        self.body.addWidget(err)
        self.body.addStretch(1)

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
        if failure == "user_ignored" or item.get("state") == "IGNORED":
            return "Игнорируется пользователем"
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
            "DDS Companion — Игнорировать медиафайл",
            "Игнорировать эту проблему?\n\n"
            "Файл останется в архиве как метаданные, но не будет удерживать Media Backfill в LIMITED. "
            "Позже его можно снова выбрать и нажать «Повторить».",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.on_media_ignore(str(issue.get("media_key")))

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
        QMessageBox.information(self, "DDS Companion — Медиафайл", text)

    def update_snapshot(self, snapshot: dict) -> None:
        health = snapshot.get("health", {})
        state = health.get("state", "UNKNOWN")
        self.overall_pill.setText(state)
        set_state_property(self.overall_pill, state)
        self.overall_hint.setText(
            health.get("summary")
            or ("Все ключевые подсистемы работают штатно" if state == "RUNNING" else "Требуется внимание")
        )
        self.overall_pill.setToolTip(health.get("tooltip") or self.overall_hint.text())
        subs = health.get("subsystems", {})
        media_details = (subs.get("media", {}) or {}).get("details", {}) or {}
        issues = list(media_details.get("attention_items") or [])
        selected_before = self._selected_media_issue()
        selected_key = str(selected_before.get("media_key")) if selected_before else None
        self._media_issue_by_key = {str(item.get("media_key")): item for item in issues if item.get("media_key")}
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
            state_text = "Игнорируется" if issue.get("state") == "IGNORED" else "Требует внимания"
            self.media_issue_table.setItem(row, 2, QTableWidgetItem(state_text))
            if selected_key and str(issue.get("media_key") or "") == selected_key:
                selected_row = row
        attention_count = int(media_details.get("attention_count") or 0)
        ignored_count = int(media_details.get("ignored") or 0)
        if issues:
            parts = []
            if attention_count:
                parts.append(self._attention_count_text(attention_count))
            if ignored_count:
                parts.append(f"Игнорируется: {ignored_count}")
            self.media_attention_summary.setText(" · ".join(parts) or "Медиа-проблем нет")
            self.media_attention.setVisible(True)
            if selected_row >= 0:
                self.media_issue_table.selectRow(selected_row)
            elif self.media_issue_table.rowCount() and self.media_issue_table.currentRow() < 0:
                self.media_issue_table.selectRow(0)
        else:
            self.media_attention.setVisible(False)
        self._update_media_action_state()

        for key, (_, state_label, summary_label, updated_label) in self.cards.items():
            info = subs.get(key, {})
            sub_state = info.get("state", "UNKNOWN")
            state_label.setText(sub_state)
            state_label.setStyleSheet(f"color:{state_color(sub_state)};font-weight:750;")
            summary = info.get("summary", "—")
            state_label.setToolTip(summary)
            summary_label.setText(summary)
            if key == "discord":
                updated_label.setText(f"Checked: {local_time(info.get('updated_at'), seconds=True)}")
            elif key == "plugin":
                details = info.get("details", {})
                version = details.get("plugin_version") or details.get("manifest_version") or "—"
                updated_label.setText(
                    f"Version: {version}  ·  Heartbeat: {local_time(info.get('updated_at'), seconds=True)}"
                )
            elif key == "updates":
                details = info.get("details", {})
                interval = details.get("interval_hours", "—")
                attempt = local_time(details.get("last_attempt_at"), seconds=True)
                next_check = local_time(details.get("next_check_at"), seconds=True)
                updated_label.setText(
                    f"Interval: {interval} h  ·  Last attempt: {attempt}  ·  Next: {next_check}"
                )
            elif key == "importer":
                updated_label.setText(f"Last import: {local_time(info.get('updated_at'), seconds=True)}")
            elif key == "watcher":
                updated_label.setText(f"Heartbeat: {local_time(info.get('updated_at'), seconds=True)}")
            else:
                updated_label.setText(f"Checked: {local_time(info.get('updated_at'), seconds=True)}")
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
        self._last_report_available = False

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
        archive_layout.addWidget(SectionHeader("Архив", "Информационный экран без опасных действий"))
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
        archive_note = QLabel("Удаление и retention архива намеренно не реализованы: данные архива не являются кэшем.")
        archive_note.setObjectName("SectionHint")
        archive_note.setWordWrap(True)
        archive_layout.addWidget(archive_note)
        archive_layout.addStretch(1)

        diagnostics, diag_layout = self._make_scroll_page()
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
            "Снимок версий, Статуса, путей, хранилища и unresolved failures.",
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
            "PRAGMA quick_check через отдельное read connection.",
            control=db_check,
        ))
        diag_layout.addWidget(self.db_check_status)

        self.copy_report = QPushButton("Копировать отчёт")
        self.copy_report.setProperty("secondary", True)
        self.copy_report.setEnabled(False)
        self.copy_report.clicked.connect(on_copy_report)
        diag_layout.addWidget(SettingRow(
            "Последний отчёт",
            "Копирует последний diagnostics report в буфер обмена.",
            control=self.copy_report,
        ))
        self.version_value = QLabel("—")
        self.plugin_value = QLabel("—")
        self.contract_value = QLabel("—")
        for title, hint, label in [
            ("Версия Companion", "Текущая версия приложения", self.version_value),
            ("Версия плагина", "Версия из heartbeat/manifest", self.plugin_value),
            ("Контракт захвата", "Версия capture schema / heartbeat contract", self.contract_value),
        ]:
            label.setStyleSheet(f"color:{TEXT};font-weight:650;")
            diag_layout.addWidget(SettingRow(title, hint, control=label))
        diag_layout.addStretch(1)

        self.tabs.addTab(general, "Общие")
        self.tabs.addTab(storage, "Хранилище")
        self.tabs.addTab(archive, "Архив")
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

        settings = snapshot.get("settings", {})
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
        self.contract_value.setText(f"capture {capture_schema} · {heartbeat_schema}")

    def set_diagnostic_status(self, text: str, *, report_available: bool = False) -> None:
        self.diag_status.setText(text)
        self.copy_report.setEnabled(report_available)
        self._last_report_available = report_available

    def set_database_check_status(self, text: str) -> None:
        self.db_check_status.setText(text)

