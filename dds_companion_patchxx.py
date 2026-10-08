from __future__ import annotations

import math
import os
import sys
from dataclasses import replace


def _human_bytes(value: int | float | None) -> str:
    try:
        n = float(value or 0)
    except Exception:
        n = 0.0
    units = ("B", "KB", "MB", "GB", "TB")
    idx = 0
    while n >= 1024.0 and idx < len(units) - 1:
        n /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(n)} {units[idx]}"
    if n >= 100:
        return f"{n:.0f} {units[idx]}"
    if n >= 10:
        return f"{n:.1f} {units[idx]}"
    return f"{n:.2f} {units[idx]}"


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _fmt_count(value) -> str:
    return f"{_safe_int(value):,}".replace(",", " ")



_NETWORK_RETRY_INTERVAL_SECONDS = 30 * 60
_TRANSIENT_NETWORK_MARKERS = (
    "timed out",
    "timeout",
    "temporary failure",
    "temporarily unavailable",
    "connection reset",
    "connection aborted",
    "connection refused",
    "network is unreachable",
    "getaddrinfo failed",
    "name or service not known",
)


def _is_transient_network_failure(failure_class, http_status, error) -> bool:
    """Recognize terminalized failures that are still routine network recovery.

    The existing downloader already performs its short bounded retry burst.  0.8.4
    only re-arms the exhausted item on a much slower cadence when there was no
    HTTP response and the recorded error still looks like a temporary connectivity
    failure.  Certificate/auth/content failures are deliberately not swept in.
    """
    failure = str(failure_class or "").strip().lower()
    if failure not in {"retry_exhausted", "network_or_io"}:
        return False
    if http_status not in (None, "", 0, "0"):
        return False
    message = str(error or "").strip().lower()
    return bool(message and any(marker in message for marker in _TRANSIENT_NETWORK_MARKERS))


def _is_transient_network_attention_item(item) -> bool:
    if not isinstance(item, dict):
        return False
    http_status = item.get("http_status")
    if http_status in (None, ""):
        http_status = item.get("last_http_status")
    error = item.get("error") or item.get("last_error")
    return _is_transient_network_failure(
        item.get("failure_class"),
        http_status,
        error,
    )


def _transient_network_reason() -> str:
    return "Временная проблема с подключением к Discord"


def _transient_network_tip() -> str:
    return (
        "Возможное решение: повторите загрузку после восстановления интернета или VPN. "
        "DDS также попробует снова автоматически через 30 минут."
    )


def _parse_iso_utc(value):
    # datetime is imported lazily so the overlay keeps the same small import surface
    # until the media patch is actually installed.
    from datetime import datetime, timezone

    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _rearm_due_transient_network_failures(service, registry_mod) -> int:
    """Re-arm due terminal network failures at most once per 30-minute window.

    We intentionally use the terminal row's updated_at as the retry clock.  A new
    failed burst updates that timestamp, so the next background re-arm cannot happen
    until another 30 minutes have elapsed.  Rows with unparseable timestamps stay
    visible/actionable instead of being guessed into recovery.
    """
    now_text = registry_mod.utc_now()
    now_dt = _parse_iso_utc(now_text)
    if now_dt is None:
        return 0

    rows = service.connection.execute(
        """
        SELECT media_key, updated_at, last_http_status, last_error, failure_class
        FROM media_objects
        WHERE state='FAILED_PERMANENT'
          AND failure_class IN ('retry_exhausted', 'network_or_io')
          AND current_url IS NOT NULL
          AND TRIM(current_url) <> ''
          AND EXISTS(SELECT 1 FROM media_refs mr WHERE mr.media_key=media_objects.media_key)
        ORDER BY updated_at, media_key
        LIMIT 100
        """
    ).fetchall()

    due_keys = []
    for row in rows:
        try:
            failure_class = row["failure_class"]
            http_status = row["last_http_status"]
            error = row["last_error"]
            updated_at = row["updated_at"]
            media_key = row["media_key"]
        except Exception:
            # sqlite3 may be configured for tuple rows in isolated tests/build tools.
            media_key, updated_at, http_status, error, failure_class = row
        if not _is_transient_network_failure(failure_class, http_status, error):
            continue
        failed_at = _parse_iso_utc(updated_at)
        if failed_at is None:
            continue
        if (now_dt - failed_at).total_seconds() < _NETWORK_RETRY_INTERVAL_SECONDS:
            continue
        due_keys.append(str(media_key))

    if not due_keys:
        return 0

    changed = 0
    with service.connection:
        for media_key in due_keys:
            cursor = service.connection.execute(
                """
                UPDATE media_objects
                SET state='KNOWN', updated_at=?, attempt_count=0, next_retry_at=NULL,
                    last_attempt_at=NULL, last_http_status=NULL, last_error=NULL, failure_class=NULL
                WHERE media_key=?
                  AND state='FAILED_PERMANENT'
                  AND failure_class IN ('retry_exhausted', 'network_or_io')
                """,
                (now_text, media_key),
            )
            changed += int(getattr(cursor, "rowcount", 0) or 0)
    return changed


def _is_webp_metadata_size_variance_spec(spec) -> bool:
    """Return True only for the live-proven WebP metadata-size variance family.

    Live evidence shows content_type=image/webp with a non-.webp filename while
    attachment.size differs from a complete HTTP payload.  The reason for that
    variance is intentionally not inferred here.  For this signature only, the
    metadata size is advisory; original transport-completeness checks remain active.
    """
    if spec is None:
        return False
    content_type = str(getattr(spec, "content_type", "") or "").split(";", 1)[0].strip().lower()
    filename = str(getattr(spec, "filename", "") or "").strip().lower()
    expected_size = getattr(spec, "expected_size", None)
    return bool(expected_size is not None and content_type == "image/webp" and not filename.endswith(".webp"))


def _relax_advisory_expected_size(spec):
    if not _is_webp_metadata_size_variance_spec(spec):
        return spec
    return replace(spec, expected_size=None)


def _patch_media_size_policy():
    from dds_companion.services import media_backfill_service as media_mod
    from dds_companion.services import media_registry_service as registry_mod

    cls = media_mod.MediaBackfillService
    if not getattr(cls, "_dds083_size_policy_patched", False):
        original_claim = cls._claim
        original_claim_one = cls._claim_one
        original_plan = cls.plan

        def patched_claim(self, *args, **kwargs):
            specs = original_claim(self, *args, **kwargs)
            return [_relax_advisory_expected_size(spec) for spec in specs]

        def patched_claim_one(self, *args, **kwargs):
            return _relax_advisory_expected_size(original_claim_one(self, *args, **kwargs))

        def patched_plan(self, *args, **kwargs):
            # One-time migration is intentionally deferred into the ordinary media
            # worker cycle.  At this point the runtime already has its normal
            # iteration-level failure isolation, so a migration defect cannot strand
            # the subsystem forever in STARTING before the worker loop begins.
            if not getattr(cls, "_dds083_mismatch_rearm_completed", False):
                stamp = registry_mod.utc_now()
                with self.connection:
                    self.connection.execute(
                        """
                        UPDATE media_objects
                        SET state='KNOWN', updated_at=?, attempt_count=0, next_retry_at=NULL,
                            last_attempt_at=NULL, last_http_status=NULL, last_error=NULL, failure_class=NULL
                        WHERE state='FAILED_PERMANENT'
                          AND failure_class='metadata_size_mismatch'
                          AND LOWER(COALESCE(content_type, '')) LIKE 'image/webp%'
                          AND LOWER(COALESCE(filename, '')) NOT LIKE '%.webp'
                          AND current_url IS NOT NULL
                          AND TRIM(current_url) <> ''
                        """,
                        (stamp,),
                    )
                cls._dds083_mismatch_rearm_completed = True
            _rearm_due_transient_network_failures(self, registry_mod)
            return original_plan(self, *args, **kwargs)

        cls._claim = patched_claim
        cls._claim_one = patched_claim_one
        cls.plan = patched_plan
        cls._dds083_size_policy_patched = True


_TETROMINO_BLOCK_PATTERNS = (
    (
        ("I", ((0, 0), (0, 1), (0, 2), (0, 3))),
        ("O", ((1, 0), (1, 1), (2, 0), (2, 1))),
        ("L", ((2, 2), (3, 0), (3, 1), (3, 2))),
        ("J", ((1, 2), (1, 3), (2, 3), (3, 3))),
    ),
    (
        ("I", ((0, 0), (0, 1), (0, 2), (0, 3))),
        ("T", ((1, 0), (2, 0), (2, 1), (3, 0))),
        ("T", ((1, 1), (1, 2), (1, 3), (2, 2))),
        ("L", ((2, 3), (3, 1), (3, 2), (3, 3))),
    ),
    (
        ("I", ((0, 0), (0, 1), (0, 2), (0, 3))),
        ("L", ((1, 0), (2, 0), (3, 0), (3, 1))),
        ("J", ((1, 1), (1, 2), (1, 3), (2, 3))),
        ("S", ((2, 1), (2, 2), (3, 2), (3, 3))),
    ),
    (
        ("I", ((0, 0), (0, 1), (0, 2), (0, 3))),
        ("L", ((1, 0), (2, 0), (3, 0), (3, 1))),
        ("J", ((1, 1), (1, 2), (1, 3), (2, 3))),
        ("Z", ((2, 1), (2, 2), (3, 2), (3, 3))),
    ),
    (
        ("I", ((0, 0), (0, 1), (0, 2), (0, 3))),
        ("L", ((1, 0), (2, 0), (3, 0), (3, 1))),
        ("S", ((1, 1), (2, 1), (2, 2), (3, 2))),
        ("J", ((1, 2), (1, 3), (2, 3), (3, 3))),
    ),
    (
        ("I", ((0, 0), (1, 0), (2, 0), (3, 0))),
        ("L", ((0, 1), (1, 1), (2, 1), (2, 2))),
        ("L", ((2, 3), (3, 1), (3, 2), (3, 3))),
        ("O", ((0, 2), (0, 3), (1, 2), (1, 3))),
    ),
)


def _build_tetromino_piece_layout():
    """Return the deterministic 25x8 field as 50 whole tetrominoes."""
    pieces = []
    for band_index, band_y in enumerate((4, 0)):
        for block_index in range(6):
            pattern = _TETROMINO_BLOCK_PATTERNS[(block_index + band_index * 2) % len(_TETROMINO_BLOCK_PATTERNS)]
            mirror = bool(band_index)
            block_x = block_index * 4
            for shape, cells in pattern:
                if mirror:
                    cells = tuple((3 - x, y) for x, y in cells)
                placed = tuple((block_x + x, band_y + y) for x, y in cells)
                pieces.append((shape, placed))
        pieces.append(("I", ((24, band_y), (24, band_y + 1), (24, band_y + 2), (24, band_y + 3))))
    return tuple(pieces)

def main():
    # Apply the runtime product version before the original application imports
    # its UI/core modules and builds snapshots.
    import dds_companion

    dds_companion.__version__ = "0.8.5"
    _patch_media_size_policy()

    from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
    from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )

    from dds_companion.gui import app as original_app
    from dds_companion.gui import pages as pages_mod
    from dds_companion.gui import window as window_mod

    OriginalDashboardPage = pages_mod.DashboardPage
    OriginalSettingsPage = pages_mod.SettingsPage
    OriginalHealthPage = pages_mod.HealthPage

    class TetrisField(QWidget):
        COLS = 25
        ROWS = 8
        TOTAL = COLS * ROWS
        PIECE_COUNT = TOTAL // 4
        COLORS = (
            QColor("#38D7FF"),
            QColor("#4D8CFF"),
            QColor("#7765FF"),
            QColor("#A84DFF"),
            QColor("#E24DCE"),
        )

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumHeight(210)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._pieces = _build_tetromino_piece_layout()
            self._target_pieces = 0
            self._locked_pieces = 0
            self._startup_done = False
            self._active_fall_tick = 0
            self._fall_ticks_per_piece = 4
            self._timer = QTimer(self)
            self._timer.setInterval(16)
            self._timer.timeout.connect(self._tick)

        def set_percent(self, percent: float | None):
            if percent is None:
                target = 0
            else:
                bounded = max(0.0, min(100.0, float(percent)))
                target = int(math.floor((bounded * self.PIECE_COUNT / 100.0) + 0.5))
            target = max(0, min(self.PIECE_COUNT, target))
            if target == self._target_pieces and self._startup_done:
                return

            previous = self._locked_pieces
            self._target_pieces = target
            if not self._startup_done:
                self._locked_pieces = 0
                self._active_fall_tick = 0
                # Keep the complete startup build around ~1-2 seconds for normal
                # occupancy while still making each falling piece perceptible.
                self._fall_ticks_per_piece = max(2, min(8, int(round(100.0 / max(1, target)))))
                self._startup_done = True
            elif target > previous:
                distance = target - previous
                self._active_fall_tick = 0
                self._fall_ticks_per_piece = max(2, min(6, int(round(42.0 / max(1, distance)))))
            else:
                self._active_fall_tick = 0

            if self._locked_pieces != self._target_pieces:
                self._timer.start()
            else:
                self._timer.stop()
                self.update()

        def _tick(self):
            if self._locked_pieces < self._target_pieces:
                self._active_fall_tick += 1
                if self._active_fall_tick >= self._fall_ticks_per_piece:
                    self._locked_pieces += 1
                    self._active_fall_tick = 0
            elif self._locked_pieces > self._target_pieces:
                # Shrinking the configured occupancy removes complete pieces only;
                # no partial tetrominoes are ever left behind.
                self._locked_pieces -= 1
                self._active_fall_tick = 0
            else:
                self._timer.stop()
                return

            self.update()
            if self._locked_pieces == self._target_pieces:
                self._timer.stop()

        def _piece_color(self, piece_index):
            return QColor(self.COLORS[piece_index % len(self.COLORS)])

        def _draw_piece(self, painter, rect, gap, cell_w, cell_h, piece_index, cells, row_shift=0.0):
            color = self._piece_color(piece_index)
            glow = QColor(color)
            glow.setAlpha(54)
            hi = QColor("#FFFFFF")
            hi.setAlpha(46)
            shifted = {(col, row): float(row) + float(row_shift) for col, row in cells}

            # Bridge only cells that belong to the same tetromino.  Neighbouring
            # pieces keep the normal grid gap, while the four cells of one piece
            # read as one connected Tetris shape instead of four unrelated tiles.
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            for col, row in cells:
                draw_row = shifted[(col, row)]
                x = rect.left() + gap + col * (cell_w + gap)
                y = rect.top() + gap + draw_row * (cell_h + gap)
                if (col + 1, row) in shifted:
                    painter.drawRect(QRectF(x + cell_w - 1.0, y + 2.0, gap + 2.0, max(1.0, cell_h - 4.0)))
                if (col, row + 1) in shifted:
                    painter.drawRect(QRectF(x + 2.0, y + cell_h - 1.0, max(1.0, cell_w - 4.0), gap + 2.0))

            for col, row in cells:
                draw_row = shifted[(col, row)]
                x = rect.left() + gap + col * (cell_w + gap)
                y = rect.top() + gap + draw_row * (cell_h + gap)
                cell = QRectF(x, y, cell_w, cell_h)
                # A falling piece may still be partially above the playfield.
                if cell.bottom() < rect.top() or cell.top() > rect.bottom():
                    continue
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow)
                painter.drawRoundedRect(cell.adjusted(-1.4, -1.4, 1.4, 1.4), 4, 4)
                painter.setBrush(color)
                painter.drawRoundedRect(cell, 3.5, 3.5)
                painter.setPen(QPen(hi, 1))
                painter.drawLine(cell.topLeft() + QPointF(3, 2), cell.topRight() + QPointF(-3, 2))

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = self.rect().adjusted(8, 8, -8, -8)
            radius = 14.0

            bg = QPainterPath()
            bg.addRoundedRect(QRectF(rect), radius, radius)
            painter.fillPath(bg, QColor("#090F1A"))
            painter.setPen(QPen(QColor("#27365B"), 1))
            painter.drawPath(bg)

            gap = 3.0
            cell_w = (rect.width() - gap * (self.COLS + 1)) / self.COLS
            cell_h = (rect.height() - gap * (self.ROWS + 1)) / self.ROWS
            if cell_w <= 1 or cell_h <= 1:
                return

            # Draw the quiet empty grid first.
            empty = QColor("#111827")
            empty_edge = QColor("#1D2A43")
            for row in range(self.ROWS):
                for col in range(self.COLS):
                    x = rect.left() + gap + col * (cell_w + gap)
                    y = rect.top() + gap + row * (cell_h + gap)
                    cell = QRectF(x, y, cell_w, cell_h)
                    painter.setPen(QPen(empty_edge, 1))
                    painter.setBrush(empty)
                    painter.drawRoundedRect(cell, 3.5, 3.5)

            # Settled whole tetrominoes.
            for piece_index in range(min(self._locked_pieces, len(self._pieces))):
                _shape, cells = self._pieces[piece_index]
                self._draw_piece(painter, rect, gap, cell_w, cell_h, piece_index, cells)

            # One active piece falls from above the field to its exact final cells.
            if self._locked_pieces < self._target_pieces and self._locked_pieces < len(self._pieces):
                piece_index = self._locked_pieces
                _shape, cells = self._pieces[piece_index]
                max_row = max(row for _col, row in cells)
                start_shift_rows = -float(max_row + 1)
                progress = min(1.0, self._active_fall_tick / max(1.0, float(self._fall_ticks_per_piece)))
                eased = 1.0 - ((1.0 - progress) ** 3)
                row_shift = start_shift_rows * (1.0 - eased)
                self._draw_piece(painter, rect, gap, cell_w, cell_h, piece_index, cells, row_shift=row_shift)

    class MediaStateCard(QFrame):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("DDSMediaStateCard")
            self.setMinimumWidth(245)
            self.setMaximumWidth(320)
            self.setStyleSheet(
                "QFrame#DDSMediaStateCard{background:#111723;border:1px solid #283655;border-radius:14px;}"
                "QLabel{background:transparent;}"
            )
            root = QVBoxLayout(self)
            root.setContentsMargins(18, 16, 18, 16)
            root.setSpacing(12)
            title = QLabel("Состояние медиа")
            title.setStyleSheet("font-size:14pt;font-weight:750;color:#F5F7FF;")
            root.addWidget(title)
            self.available = self._row(root, "Доступно", "#46E6A5")
            self.unresolved = self._row(root, "Ждут переобнаружения", "#FFC84A")
            self.attention = self._row(root, "Требуют внимания", "#FF5F75")
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color:#29364F;")
            root.addWidget(line)
            self.fill = self._row(root, "Заполнено", "#52C8FF")
            root.addStretch(1)

        def _row(self, layout, caption, color):
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color};font-size:10pt;")
            text = QLabel(caption)
            text.setStyleSheet("color:#B8C7E7;font-size:10.5pt;")
            value = QLabel("—")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value.setStyleSheet("color:#F6F8FF;font-size:11pt;font-weight:750;")
            row.addWidget(dot)
            row.addWidget(text, 1)
            row.addWidget(value)
            layout.addLayout(row)
            return value

    class CacheOverviewPanel(QFrame):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("DDSCacheOverview")
            self.setStyleSheet(
                "QFrame#DDSCacheOverview{background:#101620;border:1px solid #29364F;border-radius:14px;}"
                "QLabel{background:transparent;}"
            )
            outer = QVBoxLayout(self)
            outer.setContentsMargins(16, 15, 16, 15)
            outer.setSpacing(12)

            title = QLabel("Media Cache")
            title.setStyleSheet("font-size:15pt;font-weight:800;color:#F7F8FF;")
            subtitle = QLabel("Заполнение локального медиакэша относительно заданного лимита")
            subtitle.setStyleSheet("color:#8FA6CF;font-size:9.5pt;")
            outer.addWidget(title)
            outer.addWidget(subtitle)

            content = QHBoxLayout()
            content.setSpacing(14)
            left = QVBoxLayout()
            left.setSpacing(10)
            self.field = TetrisField(self)
            left.addWidget(self.field, 1)

            stats = QHBoxLayout()
            stats.setSpacing(18)
            self.capacity = QLabel("—")
            self.percent = QLabel("—")
            self.count = QLabel("—")
            for label in (self.capacity, self.percent, self.count):
                label.setStyleSheet("color:#F5F7FF;font-size:11pt;font-weight:700;")
            stats.addWidget(self.capacity)
            stats.addStretch(1)
            stats.addWidget(self.percent)
            stats.addStretch(1)
            stats.addWidget(self.count)
            left.addLayout(stats)

            self.state = MediaStateCard(self)
            content.addLayout(left, 1)
            content.addWidget(self.state)
            outer.addLayout(content, 1)

        def update_from_snapshot(self, snapshot):
            stats = (snapshot or {}).get("stats") or {}
            settings = (snapshot or {}).get("settings") or {}
            media_bytes = _safe_int(stats.get("media_bytes"), 0)
            limit = settings.get("media_cache_limit_bytes")
            limit_int = _safe_int(limit, 0) if limit is not None else 0
            percent = None
            if limit_int > 0:
                percent = max(0.0, min(100.0, media_bytes * 100.0 / limit_int))
                self.capacity.setText(f"{_human_bytes(media_bytes)} из {_human_bytes(limit_int)}")
                self.percent.setText(f"{percent:.0f}% заполнено")
                self.state.fill.setText(f"{percent:.0f}%")
            else:
                self.capacity.setText(f"{_human_bytes(media_bytes)} · без лимита")
                self.percent.setText("Без ограничений")
                self.state.fill.setText("—")
            media_count = max(
                _safe_int(stats.get("known_media"), 0),
                _safe_int(stats.get("cached_media_files"), 0),
            )
            self.count.setText(f"{_fmt_count(media_count)} медиафайлов")
            self.state.available.setText(_fmt_count(stats.get("cached_media_files")))
            self.state.unresolved.setText(_fmt_count(stats.get("media_unresolved")))
            self.state.attention.setText(_fmt_count(stats.get("media_attention")))
            self.field.set_percent(percent)

    class AboutBanner(QWidget):
        def __init__(self, image_path, parent=None):
            super().__init__(parent)
            self._pixmap = QPixmap(str(image_path))
            self.setMinimumHeight(200)
            self.setMaximumHeight(360)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        def hasHeightForWidth(self):
            return True

        def heightForWidth(self, width):
            if self._pixmap.isNull() or self._pixmap.width() <= 0:
                return 220
            target = int(round(width * self._pixmap.height() / self._pixmap.width()))
            return max(200, min(360, target))

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = self.rect().adjusted(0, 0, -1, -1)
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 14, 14)
            painter.setClipPath(path)
            painter.fillRect(rect, QColor("#0A0E18"))
            if not self._pixmap.isNull():
                scaled = self._pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = rect.x() + (rect.width() - scaled.width()) // 2
                y = rect.y() + (rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            painter.setClipping(False)
            painter.setPen(QPen(QColor("#29395E"), 1))
            painter.drawRoundedRect(QRectF(rect), 14, 14)

    class PatchedDashboardPage(OriginalDashboardPage):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._dds_legacy_storage = self.storage_detail
            panel = CacheOverviewPanel(self)
            idx = self.lower_grid.indexOf(self._dds_legacy_storage)
            if idx >= 0:
                row, col, row_span, col_span = self.lower_grid.getItemPosition(idx)
                self.lower_grid.removeWidget(self._dds_legacy_storage)
                self._dds_legacy_storage.hide()
                self.storage_detail = panel
                self.lower_grid.addWidget(panel, row, col, row_span, col_span)
            else:
                self.storage_detail = panel
                self.lower_grid.addWidget(panel, 0, 0, 1, 2)
            self._dds_cache_panel = panel
            self._dds_prefer_cache_first()
            if getattr(self, "latest_snapshot", None):
                self._dds_cache_panel.update_from_snapshot(self.latest_snapshot)

        def _dds_prefer_cache_first(self):
            try:
                ai = self.lower_grid.indexOf(self.activity_card)
                si = self.lower_grid.indexOf(self.storage_detail)
                if ai < 0 or si < 0:
                    return
                apos = self.lower_grid.getItemPosition(ai)
                spos = self.lower_grid.getItemPosition(si)
                if apos[0] < spos[0]:
                    self.lower_grid.removeWidget(self.activity_card)
                    self.lower_grid.removeWidget(self.storage_detail)
                    self.lower_grid.addWidget(self.storage_detail, *apos)
                    self.lower_grid.addWidget(self.activity_card, *spos)
            except Exception:
                pass

        def apply_layout_profile(self, profile):
            super().apply_layout_profile(profile)
            if hasattr(self, "_dds_cache_panel"):
                self._dds_prefer_cache_first()

        def update_snapshot(self, snapshot):
            super().update_snapshot(snapshot)
            if hasattr(self, "_dds_cache_panel"):
                self._dds_cache_panel.update_from_snapshot(snapshot)

    class PatchedHealthPage(OriginalHealthPage):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.media_retry_all_button = QPushButton("Повторить всё")
            self.media_retry_all_button.setToolTip(
                "Повторить загрузку всех текущих медиафайлов, требующих внимания."
            )
            self.media_retry_all_button.clicked.connect(self._retry_all_media)
            self._dds_insert_retry_all_button()
            self._update_media_action_state()

        def _dds_insert_retry_all_button(self):
            target = getattr(self, "media_retry_button", None)
            if target is None:
                return

            def find_layout(layout):
                if layout is None:
                    return None
                for index in range(layout.count()):
                    item = layout.itemAt(index)
                    if item.widget() is target:
                        return layout, index
                    nested = item.layout()
                    found = find_layout(nested)
                    if found is not None:
                        return found
                return None

            # HealthPage itself does not necessarily own the nested action-row
            # layout. Walk upward from the existing Retry button and search each
            # real parent layout so Retry All lands beside Retry, not as a full-row
            # maintenance control at the bottom of the card.
            parent = target.parentWidget()
            seen_layouts = set()
            while parent is not None:
                root_layout = parent.layout()
                if root_layout is not None and id(root_layout) not in seen_layouts:
                    seen_layouts.add(id(root_layout))
                    found = find_layout(root_layout)
                    if found is not None:
                        layout, index = found
                        if hasattr(layout, "insertWidget"):
                            current = layout.indexOf(self.media_retry_all_button)
                            if current != index + 1:
                                layout.insertWidget(index + 1, self.media_retry_all_button)
                            self.media_retry_all_button.show()
                            return
                parent = parent.parentWidget()

        @staticmethod
        def _human_media_reason(item):
            if _is_transient_network_attention_item(item):
                return _transient_network_reason()
            return OriginalHealthPage._human_media_reason(item)

        def _retry_all_media(self):
            callback = getattr(self, "on_media_retry", None)
            issues = list(getattr(self, "_media_issue_by_key", {}).values())
            if callback is None:
                return
            # The Status snapshot is deliberately bounded, and this action mirrors
            # the exact set of current actionable rows the user can see.
            for issue in issues:
                if str(issue.get("state") or "").upper() == "IGNORED":
                    continue
                media_key = str(issue.get("media_key") or "").strip()
                if media_key:
                    callback(media_key)

        def _update_media_action_state(self):
            super()._update_media_action_state()
            button = getattr(self, "media_retry_all_button", None)
            if button is not None:
                button.setEnabled(int(getattr(self, "_media_attention_count", 0) or 0) > 0)

        def update_snapshot(self, snapshot):
            super().update_snapshot(snapshot)
            table = getattr(self, "media_issue_table", None)
            issues = getattr(self, "_media_issue_by_key", {})
            if table is None:
                return
            for row in range(table.rowCount()):
                key_item = table.item(row, 0)
                if key_item is None:
                    continue
                media_key = str(key_item.data(Qt.UserRole) or "")
                issue = issues.get(media_key)
                if not _is_transient_network_attention_item(issue):
                    continue
                tip = _transient_network_tip()
                for column in range(table.columnCount()):
                    cell = table.item(row, column)
                    if cell is not None:
                        cell.setToolTip(tip)

    class PatchedSettingsPage(OriginalSettingsPage):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._dds_about_version = None
            self._dds_about_plugin = None
            self._dds_about_contract = None
            self._dds_hide_diagnostic_identity()
            self._dds_add_about_tab()

        def _dds_hide_diagnostic_identity(self):
            try:
                diag_widget = None
                for i in range(self.tabs.count()):
                    if self.tabs.tabText(i) == "Диагностика":
                        diag_widget = self.tabs.widget(i)
                        break
                if diag_widget is None:
                    return
                labels = diag_widget.findChildren(QLabel)
                for label in labels:
                    if label.text().strip() == "DDS — Discord Data Snatcher":
                        # The label's immediate parent is the branding block.
                        # Hiding one level higher hides the entire Diagnostics content.
                        brand_block = label.parentWidget()
                        if brand_block and brand_block is not diag_widget:
                            brand_block.hide()
                        else:
                            label.hide()
                        break
            except Exception:
                pass

        def _dds_add_about_tab(self):
            page = QWidget()
            outer = QVBoxLayout(page)
            outer.setContentsMargins(0, 0, 0, 0)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setFrameShape(QFrame.NoFrame)
            content = QWidget()
            layout = QVBoxLayout(content)
            layout.setContentsMargins(0, 4, 4, 8)
            layout.setSpacing(14)

            root = str(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
            banner_path = os.path.join(root, "assets", "DDS_about_banner_v1.png")
            layout.addWidget(AboutBanner(banner_path, content))

            title = QLabel("DDS — Discord Data Snatcher")
            title.setStyleSheet("font-size:18pt;font-weight:800;color:#F6F8FF;")
            layout.addWidget(title)
            desc = QLabel("Companion · локальный архив и медиаслой DDS")
            desc.setStyleSheet("color:#9AB0D7;font-size:10.5pt;")
            layout.addWidget(desc)

            info = QFrame()
            info.setObjectName("DDSAboutInfo")
            info.setStyleSheet(
                "QFrame#DDSAboutInfo{background:#111723;border:1px solid #29364F;border-radius:14px;}"
                "QLabel{background:transparent;}"
            )
            grid = QVBoxLayout(info)
            grid.setContentsMargins(18, 16, 18, 16)
            grid.setSpacing(10)
            self._dds_about_version = self._dds_info_row(grid, "Версия Companion", "0.8.5")
            self._dds_about_plugin = self._dds_info_row(grid, "Версия Plugin", "—")
            self._dds_about_contract = self._dds_info_row(grid, "Контракт захвата", "—")
            self._dds_info_row(grid, "Авторы", "Mr_Dexter_Morgan · Masya")
            layout.addWidget(info)

            privacy = QLabel("Локальные данные остаются на вашем компьютере")
            privacy.setWordWrap(True)
            privacy.setStyleSheet(
                "padding:12px 14px;background:#10201E;border:1px solid #214A42;"
                "border-radius:10px;color:#8FE8C9;font-size:10.5pt;font-weight:650;"
            )
            layout.addWidget(privacy)

            copy_btn = QPushButton("Копировать сведения о версии")
            copy_btn.setMinimumHeight(38)
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.setStyleSheet(
                "QPushButton{background:#171F31;border:1px solid #5367A8;border-radius:8px;"
                "padding:8px 14px;color:#DCE6FF;font-size:10pt;font-weight:650;}"
                "QPushButton:hover{background:#202B43;border-color:#728BEE;color:#FFFFFF;}"
                "QPushButton:pressed{background:#111827;border-color:#566DD2;}"
            )
            copy_btn.clicked.connect(self._dds_copy_version_info)
            layout.addWidget(copy_btn, 0, Qt.AlignLeft)
            layout.addStretch(1)
            scroll.setWidget(content)
            outer.addWidget(scroll)
            self._dds_about_page = page
            self.tabs.addTab(page, "О программе")

        def _dds_info_row(self, layout, caption, value):
            row = QHBoxLayout()
            left = QLabel(caption)
            left.setStyleSheet("color:#9EB0D1;font-size:10pt;")
            right = QLabel(value)
            right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            right.setTextInteractionFlags(Qt.TextSelectableByMouse)
            right.setStyleSheet("color:#F5F7FF;font-size:10.5pt;font-weight:700;")
            row.addWidget(left)
            row.addStretch(1)
            row.addWidget(right)
            layout.addLayout(row)
            return right

        def _dds_copy_version_info(self):
            companion = self._dds_about_version.text() if self._dds_about_version else "0.8.5"
            plugin = self._dds_about_plugin.text() if self._dds_about_plugin else "—"
            contract = self._dds_about_contract.text() if self._dds_about_contract else "—"
            text = "\n".join((
                f"DDS Companion: {companion}",
                f"DDS Plugin: {plugin}",
                f"Контракт захвата: {contract}",
                f"Windows: {sys.getwindowsversion().major}.{sys.getwindowsversion().minor}.{sys.getwindowsversion().build}",
            ))
            QApplication.clipboard().setText(text)

        def update_snapshot(self, snapshot):
            super().update_snapshot(snapshot)
            try:
                if self._dds_about_version is not None:
                    value = self.version_value.text().strip() if hasattr(self, "version_value") else "0.8.5"
                    self._dds_about_version.setText(value or "0.8.5")
                if self._dds_about_plugin is not None:
                    value = self.plugin_value.text().strip() if hasattr(self, "plugin_value") else "—"
                    self._dds_about_plugin.setText(value or "—")
                if self._dds_about_contract is not None:
                    value = self.contract_value.text().strip() if hasattr(self, "contract_value") else "—"
                    self._dds_about_contract.setText(value or "—")
            except Exception:
                pass

    # Patch every live reference that can instantiate these pages.
    pages_mod.DashboardPage = PatchedDashboardPage
    pages_mod.SettingsPage = PatchedSettingsPage
    pages_mod.HealthPage = PatchedHealthPage
    if hasattr(window_mod, "DashboardPage"):
        window_mod.DashboardPage = PatchedDashboardPage
    if hasattr(window_mod, "SettingsPage"):
        window_mod.SettingsPage = PatchedSettingsPage
    if hasattr(window_mod, "HealthPage"):
        window_mod.HealthPage = PatchedHealthPage

    return original_app.main()
