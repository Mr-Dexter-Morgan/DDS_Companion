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

from .theme import ACCENT, DANGER, DIM, INFO, MUTED, SUCCESS, TEXT, WARNING


def human_size(value: int | float | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if number < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{sign}{int(number)} B"
            return f"{sign}{number:.2f} {unit}"
        number /= 1024
    return f"{sign}{number:.2f} TB"


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
    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
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
        layout.addLayout(line)
        layout.addWidget(self.bar)

    def set_value(self, value: int, total: int) -> None:
        self.value.setText(human_size(value))
        ratio = 0 if total <= 0 else min(1.0, value / total)
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
            QMessageBox.warning(self, "DDS Companion", detail)
