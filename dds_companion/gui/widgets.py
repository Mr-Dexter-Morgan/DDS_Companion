from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dds_companion.core.formatting import human_size, human_storage_delta

from .theme import ACCENT, DANGER, DIM, INFO, MUTED, SUCCESS, TEXT, WARNING


def signed_size(value: int | float | None) -> str:
    if value is None:
        return "—"
    prefix = "+" if value >= 0 else ""
    return prefix + human_size(value)


def local_time(value: str | None, *, seconds: bool = False) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo:
            dt = dt.astimezone()
        fmt = "%d.%m.%Y %H:%M:%S" if seconds else "%d.%m.%Y %H:%M"
        return dt.strftime(fmt)
    except (ValueError, TypeError):
        return str(value)


def state_color(state: str) -> str:
    return {
        "RUNNING": SUCCESS,
        "STARTING": INFO,
        "LIMITED": WARNING,
        "DEGRADED": WARNING,
        "STALE": WARNING,
        "WAITING": MUTED,
        "UPDATE AVAILABLE": WARNING,
        "FAILED": WARNING,
        "OK": SUCCESS,
        "NEVER": MUTED,
        "NOT RUNNING": MUTED,
        "ERROR": DANGER,
        "STOPPED": MUTED,
    }.get((state or "").upper(), DIM)



_ACTIVITY_SUBSYSTEMS = {
    "runtime": "Companion",
    "importer": "Импорт",
    "watcher": "Наблюдение",
    "health": "Состояние",
    "media": "Медиа",
    "database": "База данных",
    "dds_data": "DDS_Data",
    "discord": "Discord",
    "plugin": "DDS Plugin",
    "updates": "Обновления",
}

_ACTIVITY_EVENTS = {
    "session_started": "Запуск",
    "session_stopped": "Завершение",
    "session_completed": "Завершение",
    "startup_sync": "Начальная синхронизация",
    "capture_imported": "Импорт данных",
    "capture_failed": "Ошибка импорта",
    "capture_removed": "Удаление capture",
    "watcher_crashed": "Ошибка наблюдения",
    "gui_runtime_crashed": "Ошибка Companion",
    "media_backfill_enabled": "Автозагрузка включена",
    "media_backfill_disabled": "Автозагрузка выключена",
    "media_cached": "Медиа сохранено",
    "media_cache_maintenance": "Обслуживание кэша",
    "media_manual_clear_requeued": "Повторная постановка",
    "media_user_retry": "Повтор загрузки",
    "media_user_ignored": "Проблема обработана",
    "media_user_ignored_all": "Проблемы обработаны",
    "media_processed_cleared": "Обработанные очищены",
    "media_registry_bootstrap": "Реестр медиа",
    "media_worker_iteration_failed": "Ошибка загрузчика медиа",
    "health_initial_state": "Состояние системы",
    "health_state_changed": "Состояние изменилось",
    "health_reason_changed": "Причина изменилась",
    "health_recovered": "Система восстановилась",
}


def human_activity_subsystem(value: str | None) -> str:
    key = str(value or "").strip().lower()
    return _ACTIVITY_SUBSYSTEMS.get(key, value or "—")


def human_activity_event(value: str | None) -> str:
    key = str(value or "").strip()
    return _ACTIVITY_EVENTS.get(key, key or "—")


def human_activity_level(value: str | None) -> str:
    return {"INFO": "Инфо", "WARNING": "Внимание", "ERROR": "Ошибка"}.get(
        str(value or "INFO").upper(), str(value or "—")
    )


def _human_health_reasons(reasons: list[dict]) -> str:
    labels = {
        "database-error": "ошибка базы данных",
        "unresolved-failures": "есть неразрешённые ошибки импорта",
        "source-missing": "DDS_Data недоступна",
        "importer-limited": "импорт требует внимания",
        "watcher-limited": "наблюдение требует внимания",
        "discord-not-running": "Discord не запущен",
        "plugin-not-ready": "DDS Plugin не готов",
    }
    values = []
    for item in reasons or []:
        code = str(item.get("code") or "")
        values.append(labels.get(code, human_activity_subsystem(item.get("subsystem"))))
    return " · ".join(dict.fromkeys(values))


def human_activity_summary(event: dict | None) -> str:
    event = event or {}
    event_type = str(event.get("event_type") or "")
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    if event_type == "startup_sync":
        return (
            f"Начальная синхронизация: +{int(event.get('messages_new') or 0)} новых, "
            f"{int(event.get('messages_refreshed') or 0)} обновлено, "
            f"{int(details.get('failed') or 0)} ошибок"
        )
    if event_type == "capture_imported":
        return (
            f"Импортировано: +{int(event.get('messages_new') or 0)} сообщений, "
            f"{int(event.get('messages_refreshed') or 0)} обновлено"
        )
    if event_type == "session_started":
        return "DDS запущен"
    if event_type in {"session_stopped", "session_completed"}:
        return "DDS завершил работу штатно"
    if event_type == "media_backfill_enabled":
        return "Автоматическая загрузка медиа включена"
    if event_type == "media_backfill_disabled":
        return "Автоматическая загрузка медиа выключена"
    if event_type == "media_cached":
        size = details.get("local_size")
        if size is not None:
            return f"Медиа сохранено в кэш: {human_size(int(size))}"
        return "Медиа сохранено в кэш"
    if event_type == "media_manual_clear_requeued":
        return f"После очистки кэша повторно поставлено в очередь: {int(details.get('requeued') or 0)}"
    if event_type == "media_user_ignored_all":
        return f"Обработано проблемных медиа: {int(details.get('changed') or 0)}"
    if event_type == "media_processed_cleared":
        return (
            f"Очищено обработанных медиа: {int(details.get('changed') or 0)}; "
            "ожидают свежую ссылку Discord"
        )
    if event_type == "media_user_ignored":
        return "Проблема медиа отмечена как обработанная"
    if event_type == "media_user_retry":
        return "Запущена ручная повторная загрузка медиа"
    if event_type == "media_cache_maintenance":
        removed = int(details.get("files_removed") or 0)
        errors = int(details.get("errors") or 0)
        return f"Обслуживание медиакэша: удалено {removed}, ошибок {errors}"
    if event_type.startswith("health_"):
        state = str(details.get("state") or "UNKNOWN")
        previous = str(details.get("previous_state") or "")
        reason_text = _human_health_reasons(details.get("reasons") or [])
        if event_type == "health_recovered":
            return f"Состояние: {previous or '—'} → RUNNING — все контролируемые компоненты восстановились"
        prefix = f"Состояние: {previous} → {state}" if previous and previous != state else f"Состояние: {state}"
        return prefix + (f" — {reason_text}" if reason_text else "")
    if event_type == "capture_failed":
        return "Не удалось импортировать capture"
    if event_type == "capture_removed":
        return "Capture удалён; архивные данные сохранены"
    if event_type == "watcher_crashed":
        return "Наблюдение за DDS_Data остановилось из-за ошибки"
    if event_type == "gui_runtime_crashed":
        return "Companion остановился из-за неожиданной ошибки"
    if event_type == "media_worker_iteration_failed":
        return "Ошибка загрузчика медиа; повтор будет выполнен позже"
    return str(event.get("summary") or "—")


def human_health_summary(subsystem: str, info: dict | None) -> str:
    info = info or {}
    state = str(info.get("state") or "UNKNOWN").upper()
    details = info.get("details") if isinstance(info.get("details"), dict) else {}
    key = str(subsystem or "").lower()
    if key == "database":
        return "SQLite: проверка целостности пройдена" if state == "RUNNING" else "База данных требует внимания"
    if key == "dds_data":
        return "DDS_Data доступна" if state == "RUNNING" else "DDS_Data недоступна"
    if key == "importer":
        return "Импорт работает штатно" if state == "RUNNING" else "Импорт требует внимания"
    if key == "watcher":
        if state == "RUNNING":
            return "Наблюдение за DDS_Data активно"
        if state == "WAITING":
            return "Ожидание DDS_Data"
        return "Наблюдение за DDS_Data не активно"
    if key == "discord":
        return "Discord запущен" if state == "RUNNING" else "Discord не запущен"
    if key == "plugin":
        version = details.get("plugin_version") or details.get("manifest_version")
        if state == "RUNNING":
            return f"DDS Plugin {version or ''} активен".strip()
        if state == "UPDATE AVAILABLE":
            return "Для DDS Plugin доступно необходимое обновление"
        if state in {"NOT RUNNING", "STALE"}:
            return "DDS Plugin не передаёт актуальный heartbeat"
        return "DDS Plugin требует внимания"
    if key == "media":
        if state == "STOPPED":
            return "Автоматическая загрузка медиа выключена"
        if state == "RUNNING":
            return "Загрузка медиа работает штатно"
        return "Загрузка медиа требует внимания"
    if key == "updates":
        if state == "NEVER":
            return "Проверок обновлений ещё не было"
        return "Проверка обновлений работает" if state == "RUNNING" else "Проверка обновлений требует внимания"
    return str(info.get("summary") or "—")

def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_state_property(widget: QWidget, state: str) -> None:
    widget.setProperty("state", (state or "UNKNOWN").upper())
    repolish(widget)


def open_folder(path: str | Path, parent_on_missing: bool = True) -> tuple[bool, str]:
    target = Path(path)
    if target.is_file():
        target = target.parent
    elif not target.exists() and parent_on_missing:
        candidate = target
        while not candidate.exists() and candidate.parent != candidate:
            candidate = candidate.parent
        target = candidate
    if not target.exists():
        return False, f"Папка не существует: {path}"
    ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))
    return bool(ok), str(target.resolve())


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", True)


class MetricCard(Card):
    def __init__(self, title: str, value: str = "—", hint: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(5)

        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("CardEyebrow")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("MetricHint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_label)
        layout.addStretch(1)

    def set_data(self, value: str, hint: str | None = None) -> None:
        self.value_label.setText(value)
        if hint is not None:
            self.hint_label.setText(hint)


class SectionHeader(QWidget):
    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("SectionHint")
        texts.addWidget(title_label)
        if hint:
            texts.addWidget(hint_label)
        layout.addLayout(texts, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        layout.addLayout(self.actions)

    def add_action(self, button: QPushButton) -> None:
        self.actions.addWidget(button)


class HealthRow(QWidget):
    def __init__(self, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(10)
        self.dot = QLabel("●")
        self.dot.setFixedWidth(14)
        self.name = QLabel(name)
        self.name.setStyleSheet(f"color:{TEXT};font-weight:650;")
        self.summary = QLabel("Ожидание данных…")
        self.summary.setStyleSheet(f"color:{MUTED};")
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.state = QLabel("UNKNOWN")
        self.state.setObjectName("CardEyebrow")
        self.state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.dot)
        layout.addWidget(self.name)
        layout.addWidget(self.summary, 1)
        layout.addWidget(self.state)

    def update_state(self, state: str, summary: str) -> None:
        state = (state or "UNKNOWN").upper()
        self.dot.setStyleSheet(f"color:{state_color(state)};")
        self.state.setText(state)
        self.state.setStyleSheet(f"color:{state_color(state)};font-weight:750;")
        self.summary.setText(summary or "—")


class StorageRow(QWidget):
    def __init__(self, label: str, color: str = ACCENT, parent: QWidget | None = None):
        super().__init__(parent)
        self.color = color
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(5)
        line = QHBoxLayout()
        self.label = QLabel(label)
        self.label.setStyleSheet(f"color:{MUTED};")
        self.value = QLabel("—")
        self.value.setStyleSheet(f"color:{TEXT};font-weight:650;")
        self.value.setAlignment(Qt.AlignRight)
        line.addWidget(self.label)
        line.addStretch(1)
        line.addWidget(self.value)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(
            "QProgressBar{background:#202635;border:none;border-radius:4px;min-height:8px;}"
            f"QProgressBar::chunk{{background:{self.color};border-radius:4px;}}"
        )
        layout.addLayout(line)
        layout.addWidget(self.bar)

    def set_value(self, value: int, total: int) -> None:
        ratio = 0 if total <= 0 else min(1.0, value / total)
        percent = ratio * 100
        self.value.setText(f"{human_size(value)}  ·  {percent:.1f}%")
        self.bar.setValue(int(ratio * 1000))


class PathRow(Card):
    def __init__(self, title: str, path: str, *, open_label: str = "Открыть", parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        self.path_label = QLabel(path)
        self.path_label.setObjectName("SectionHint")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        text_box.addWidget(title_label)
        text_box.addWidget(self.path_label)
        layout.addLayout(text_box, 1)
        copy_btn = QPushButton("Копировать")
        copy_btn.setProperty("ghost", True)
        copy_btn.clicked.connect(self.copy_path)
        open_btn = QPushButton(open_label)
        open_btn.setProperty("secondary", True)
        open_btn.clicked.connect(self.open_path)
        layout.addWidget(copy_btn)
        layout.addWidget(open_btn)

    def set_path(self, path: str) -> None:
        self.path = path
        self.path_label.setText(path)

    def copy_path(self) -> None:
        QApplication.clipboard().setText(self.path)

    def open_path(self) -> None:
        ok, detail = open_folder(self.path)
        if not ok:
            QMessageBox.warning(self, "DDS", detail)


class StorageDonut(QWidget):
    """Compact storage ring used on Dashboard.

    It is intentionally presentation-only: expensive directory scanning stays in
    the background runtime and this widget only paints numbers from the snapshot.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(170, 170)
        self.setMaximumHeight(210)
        self._segments: list[tuple[str, int, str]] = []
        self._total = 0

    def set_segments(self, segments: list[tuple[str, int, str]]) -> None:
        self._segments = [(label, max(0, int(value)), color) for label, value, color in segments]
        self._total = sum(value for _label, value, _color in self._segments)
        self.update()

    def paintEvent(self, event) -> None:  # pragma: no cover - visual Qt surface
        from PySide6.QtGui import QColor, QPainter, QPen
        from PySide6.QtCore import QRectF

        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        side = min(self.width(), self.height()) - 22
        rect = QRectF(
            (self.width() - side) / 2,
            (self.height() - side) / 2,
            side,
            side,
        )
        pen_width = max(12, int(side * 0.09))
        base_pen = QPen(QColor("#202635"), pen_width)
        base_pen.setCapStyle(Qt.FlatCap)
        painter.setPen(base_pen)
        painter.drawArc(rect, 0, 360 * 16)

        total = self._total
        if total > 0:
            start = 90 * 16
            for _label, value, color in self._segments:
                if value <= 0:
                    continue
                span = -int((value / total) * 360 * 16)
                pen = QPen(QColor(color), pen_width)
                pen.setCapStyle(Qt.FlatCap)
                painter.setPen(pen)
                painter.drawArc(rect, start, span)
                start += span

        painter.setPen(QColor(TEXT))
        font = painter.font()
        font.setPointSize(15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, human_size(total))


class SettingRow(QFrame):
    """Telegram-style compact settings row with a caller-provided right control."""

    def __init__(
        self,
        title: str,
        hint: str = "",
        *,
        control: QWidget | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("settingRow", True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SettingTitle")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("SettingHint")
        self.hint_label.setWordWrap(True)
        text.addWidget(self.title_label)
        if hint:
            text.addWidget(self.hint_label)
        layout.addLayout(text, 1)
        self.control = control
        if control is not None:
            layout.addWidget(control, 0, Qt.AlignVCenter)

    def set_hint(self, hint: str) -> None:
        self.hint_label.setText(hint)
        self.hint_label.setVisible(bool(hint))
