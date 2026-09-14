from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
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
    def __init__(self, on_refresh, on_open_dds, on_open_logs, parent=None):
        super().__init__(
            "Dashboard",
            "Состояние архива, watcher и рост хранилища — всё важное в одном экране.",
            parent,
            scrollable=True,
        )
        self.latest_snapshot: dict = {}

        actions = QHBoxLayout()
        actions.setSpacing(8)
        open_dds = QPushButton("Open DDS_Data")
        open_dds.setProperty("secondary", True)
        open_dds.clicked.connect(on_open_dds)
        open_logs = QPushButton("Open logs")
        open_logs.setProperty("secondary", True)
        open_logs.clicked.connect(on_open_logs)
        refresh = QPushButton("↻  Обновить")
        refresh.setProperty("secondary", True)
        refresh.setProperty("compact", True)
        refresh.clicked.connect(on_refresh)
        actions.addWidget(open_dds)
        actions.addWidget(open_logs)
        actions.addStretch(1)
        actions.addWidget(refresh)
        self.body.addLayout(actions)

        self.metrics_grid = QGridLayout()
        metrics = self.metrics_grid
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.storage_card = MetricCard("Общее хранилище", "—", "SQLite + DDS JSON + cache/media/logs")
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

        self.health_card = Card()
        health_layout = QVBoxLayout(self.health_card)
        health_layout.setContentsMargins(16, 14, 16, 14)
        health_layout.setSpacing(4)
        health_header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Health")
        title.setObjectName("SectionTitle")
        hint = QLabel("Ключевые подсистемы")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        self.health_pill = QLabel("STARTING")
        self.health_pill.setObjectName("StatusPill")
        set_state_property(self.health_pill, "STARTING")
        health_header.addLayout(title_box, 1)
        health_header.addWidget(self.health_pill, 0, Qt.AlignTop)
        health_layout.addLayout(health_header)
        self.health_rows = {
            "database": HealthRow("Database"),
            "dds_data": HealthRow("DDS_Data"),
            "importer": HealthRow("Importer"),
            "watcher": HealthRow("Watcher"),
        }
        for row in self.health_rows.values():
            health_layout.addWidget(row)
        health_layout.addStretch(1)

        self.storage_detail = Card()
        storage_layout = QVBoxLayout(self.storage_detail)
        storage_layout.setContentsMargins(16, 14, 16, 14)
        storage_layout.setSpacing(6)
        storage_layout.addWidget(SectionHeader("Хранилище", "Распределение текущего объёма"))
        self.storage_rows = {
            "sqlite_bytes": StorageRow("SQLite + WAL/SHM"),
            "dds_json_bytes": StorageRow("DDS JSON"),
            "media_bytes": StorageRow("Media cache"),
            "cache_bytes": StorageRow("Cache"),
            "logs_bytes": StorageRow("Logs"),
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

        lower.addWidget(self.activity_card, 0, 0, 1, 2)
        lower.addWidget(self.health_card, 0, 2)
        lower.addWidget(self.storage_detail, 1, 0, 1, 2)
        lower.addWidget(self.session_card, 1, 2)
        lower.setColumnStretch(0, 1)
        lower.setColumnStretch(1, 1)
        lower.setColumnStretch(2, 1)
        lower.setRowStretch(0, 1)
        lower.setRowStretch(1, 1)
        self.body.addLayout(lower, 1)

    def apply_layout_profile(self, profile: str) -> None:
        super().apply_layout_profile(profile)

        metrics = self.metrics_grid
        lower = self.lower_grid
        for widget in (self.storage_card, self.messages_card, self.context_card, self.media_card):
            metrics.removeWidget(widget)
        for widget in (self.activity_card, self.health_card, self.storage_detail, self.session_card):
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
            lower.addWidget(self.health_card, 1, 0)
            lower.addWidget(self.storage_detail, 2, 0)
            lower.addWidget(self.session_card, 3, 0)
            lower.setColumnStretch(0, 1)
            lower.setColumnStretch(1, 0)
            lower.setColumnStretch(2, 0)
            lower.setHorizontalSpacing(0)
            lower.setVerticalSpacing(10)
        else:
            metrics.addWidget(self.storage_card, 0, 0)
            metrics.addWidget(self.messages_card, 0, 1)
            metrics.addWidget(self.context_card, 0, 2)
            metrics.addWidget(self.media_card, 0, 3)
            for col in range(4):
                metrics.setColumnStretch(col, 1)

            lower.addWidget(self.activity_card, 0, 0, 1, 2)
            lower.addWidget(self.health_card, 0, 2)
            lower.addWidget(self.storage_detail, 1, 0, 1, 2)
            lower.addWidget(self.session_card, 1, 2)
            lower.setColumnStretch(0, 1)
            lower.setColumnStretch(1, 1)
            lower.setColumnStretch(2, 1)
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

        overall = health.get("state", "UNKNOWN")
        self.health_pill.setText(overall)
        set_state_property(self.health_pill, overall)
        subsystems = health.get("subsystems", {})
        for name, row in self.health_rows.items():
            info = subsystems.get(name, {})
            row.update_state(info.get("state", "UNKNOWN"), info.get("summary", "Нет данных"))

        total = max(1, int(stats.get("total_known_storage_bytes", 0)))
        for key, row in self.storage_rows.items():
            row.set_value(int(stats.get(key, 0)), total)
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
    def __init__(self, on_open_library, parent=None):
        super().__init__(
            "Library",
            "Структура накопленного архива: Server → Channel → Thread. Поиск по сообщениям появится отдельным этапом.",
            parent,
        )
        tools = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Фильтр по серверам, каналам и тредам…")
        self.filter.textChanged.connect(self.apply_filter)
        open_btn = QPushButton("Open library folder")
        open_btn.setProperty("secondary", True)
        open_btn.clicked.connect(on_open_library)
        tools.addWidget(self.filter, 1)
        tools.addWidget(open_btn)
        self.body.addLayout(tools)

        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Архив", "Сообщения", "ID"])
        self.tree.setColumnWidth(0, 480)
        self.tree.setColumnWidth(1, 110)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.header().setStretchLastSection(True)
        layout.addWidget(self.tree)
        self.body.addWidget(card, 1)
        self._library: list[dict] = []

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
            g = QTreeWidgetItem([guild["name"], str(guild["message_count"]), guild["id"]])
            g.setData(0, Qt.UserRole, f"g:{guild['id']}")
            g.setForeground(0, QColor(TEXT))
            font = g.font(0)
            font.setBold(True)
            g.setFont(0, font)
            self.tree.addTopLevelItem(g)
            for channel in guild.get("channels", []):
                direct = channel.get("direct_message_count", 0)
                thread_total = sum(t.get("message_count", 0) for t in channel.get("threads", []))
                c = QTreeWidgetItem([
                    f"# {channel['name']}",
                    str(direct + thread_total),
                    channel["id"],
                ])
                c.setData(0, Qt.UserRole, f"c:{channel['id']}")
                c.setForeground(0, QColor("#cdd5e7"))
                g.addChild(c)
                for thread in channel.get("threads", []):
                    t = QTreeWidgetItem([
                        f"↳ {thread['name']}",
                        str(thread["message_count"]),
                        thread["id"],
                    ])
                    t.setData(0, Qt.UserRole, f"t:{thread['id']}")
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
        if selected_item:
            self.tree.setCurrentItem(selected_item)
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
        own = not needle or needle in item.text(0).casefold() or needle in item.text(2).casefold()
        child_match = False
        for i in range(item.childCount()):
            child_match |= self._filter_item(item.child(i), needle)
        visible = own or child_match
        item.setHidden(not visible)
        if needle and child_match:
            item.setExpanded(True)
        return visible


class ActivityPage(Page):
    def __init__(self, parent=None):
        super().__init__(
            "Activity",
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
    def __init__(self, parent=None):
        super().__init__(
            "Health",
            "Проверка жизненно важных подсистем, heartbeat и ошибок, которые не должны останавливать архив.",
            parent,
        )
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
            lay.addLayout(top)
            lay.addWidget(summary)
            lay.addWidget(updated)
            lay.addStretch(1)
            grid.addWidget(card, index // 2, index % 2)
            self.cards[key] = (card, state, summary, updated)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        err = Card()
        err_layout = QVBoxLayout(err)
        err_layout.setContentsMargins(16, 14, 16, 14)
        err_layout.addWidget(SectionHeader("Последняя ошибка", "Если всё чисто — здесь так и будет написано"))
        self.last_error = QLabel("Ошибок нет")
        self.last_error.setWordWrap(True)
        self.last_error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.last_error.setStyleSheet(f"color:{MUTED};")
        err_layout.addWidget(self.last_error)
        self.body.addWidget(err)
        self.body.addStretch(1)

    def update_snapshot(self, snapshot: dict) -> None:
        health = snapshot.get("health", {})
        state = health.get("state", "UNKNOWN")
        self.overall_pill.setText(state)
        set_state_property(self.overall_pill, state)
        unresolved = health.get("unresolved_failed_jobs", 0)
        self.overall_hint.setText(
            "Все ключевые подсистемы работают штатно"
            if state == "RUNNING"
            else f"Требуется внимание · unresolved failed jobs: {unresolved}"
        )
        subs = health.get("subsystems", {})
        for key, (_, state_label, summary_label, updated_label) in self.cards.items():
            info = subs.get(key, {})
            sub_state = info.get("state", "UNKNOWN")
            state_label.setText(sub_state)
            state_label.setStyleSheet(f"color:{state_color(sub_state)};font-weight:750;")
            summary_label.setText(info.get("summary", "—"))
            updated_label.setText(f"Обновлено: {local_time(info.get('updated_at'), seconds=True)}")
        last_error = health.get("last_error")
        self.last_error.setText(last_error or "Ошибок нет")
        self.last_error.setStyleSheet(f"color:{DANGER if last_error else MUTED};")


class SettingsPage(Page):
    def __init__(self, parent=None):
        super().__init__(
            "Settings",
            "Основные настройки — на первом плане. Пути и служебное хранилище вынесены отдельно.",
            parent,
        )

        self.tabs = QTabWidget()
        self.tabs.setObjectName("SettingsTabs")
        self.body.addWidget(self.tabs, 1)

        # Main settings stay lightweight and visible first.  We deliberately do
        # not expose fake/editable controls until the runtime has persistence
        # and validation for them.
        general = QWidget()
        general_layout = QVBoxLayout(general)
        general_layout.setContentsMargins(0, 14, 0, 0)
        general_layout.setSpacing(12)

        runtime = Card()
        rt = QVBoxLayout(runtime)
        rt.setContentsMargins(16, 14, 16, 14)
        rt.setSpacing(8)
        rt.addWidget(SectionHeader("Watcher policy", "Текущая политика наблюдения; пока read-only"))
        self.watcher_policy = QLabel("poll — · settle —")
        self.watcher_policy.setStyleSheet(f"color:{TEXT};font-weight:650;")
        rt.addWidget(self.watcher_policy)
        general_layout.addWidget(runtime)

        priority = Card()
        priority_layout = QVBoxLayout(priority)
        priority_layout.setContentsMargins(16, 14, 16, 14)
        priority_layout.setSpacing(6)
        priority_layout.addWidget(SectionHeader("Основные настройки", "Здесь будут пользовательские параметры Companion"))
        priority_hint = QLabel(
            "Пути больше не занимают главный экран Settings. Новые важные параметры "
            "будут добавляться сюда по мере появления их безопасного сохранения и проверки."
        )
        priority_hint.setObjectName("SectionHint")
        priority_hint.setWordWrap(True)
        priority_layout.addWidget(priority_hint)
        general_layout.addWidget(priority)
        general_layout.addStretch(1)

        paths_page = QWidget()
        paths_outer = QVBoxLayout(paths_page)
        paths_outer.setContentsMargins(0, 10, 0, 0)
        paths_outer.setSpacing(0)
        paths_scroll = QScrollArea()
        paths_scroll.setWidgetResizable(True)
        paths_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        paths_scroll.setFrameShape(QFrame.NoFrame)
        paths_content = QWidget()
        paths_content.setObjectName("SettingsPathsContent")
        paths_layout = QVBoxLayout(paths_content)
        paths_layout.setContentsMargins(0, 4, 4, 4)
        paths_layout.setSpacing(10)
        paths_layout.addWidget(SectionHeader("Paths & Storage", "Служебные пути и быстрый доступ к данным"))

        self.rows: dict[str, PathRow] = {}
        labels = [
            ("app_data", "Library / Companion data"),
            ("dds_data", "DDS_Data (plugin export)"),
            ("database", "SQLite database"),
            ("logs", "Logs"),
            ("media", "Media cache"),
            ("cache", "Cache"),
            ("backups", "Backups"),
        ]
        for key, label in labels:
            row = PathRow(label, "—")
            self.rows[key] = row
            paths_layout.addWidget(row)
        paths_layout.addStretch(1)
        paths_scroll.setWidget(paths_content)
        paths_outer.addWidget(paths_scroll, 1)

        self.tabs.addTab(general, "Основные")
        self.tabs.addTab(paths_page, "Paths & Storage")

    def update_snapshot(self, snapshot: dict) -> None:
        paths = snapshot.get("paths", {})
        for key, row in self.rows.items():
            row.set_path(paths.get(key, "—"))
        watcher = snapshot.get("watcher", {})
        self.watcher_policy.setText(
            f"poll={watcher.get('poll_ms', '—')} ms   ·   settle={watcher.get('settle_ms', '—')} ms"
        )

