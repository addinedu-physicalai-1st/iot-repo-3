"""유통기한 통계 위젯: 일별/주별/월별."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import calendar

from PyQt6.QtCore import QRectF, Qt, QDate
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCalendarWidget,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QToolTip,
)

from theme import TEXT_PRIMARY, TEXT_SECONDARY


@dataclass
class ExpLog:
    exp_date: date
    product_name: str


class WeeklyBarCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = [0] * 7
        self._start = date.today()
        self._details: list[Counter[str]] = [Counter() for _ in range(7)]
        self._bar_rects: list[QRectF] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(220)

    def set_week(
        self, start_monday: date, counts: list[int], details: list[Counter[str]] | None = None
    ) -> None:
        self._start = start_monday
        self._counts = counts[:7] + [0] * (7 - len(counts[:7]))
        if details:
            self._details = details[:7] + [Counter() for _ in range(7 - len(details[:7]))]
        else:
            self._details = [Counter() for _ in range(7)]
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        left = 34
        right = 12
        top = 16
        bottom = 42
        chart_w = max(1, w - left - right)
        chart_h = max(1, h - top - bottom)
        max_v = max(self._counts) if max(self._counts) > 0 else 1
        labels = ["월", "화", "수", "목", "금", "토", "일"]
        slot_w = chart_w / 7.0
        bar_w = min(28, slot_w * 0.52)
        self._bar_rects = []

        # baseline
        p.setPen(QPen(QColor("#d6d6d6"), 1))
        p.drawLine(left, top + chart_h, left + chart_w, top + chart_h)

        for i, val in enumerate(self._counts):
            x_center = left + slot_w * (i + 0.5)
            bar_h = chart_h * (val / max_v)
            x = x_center - bar_w / 2
            y = top + chart_h - bar_h

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#4A90D9"))
            bar_rect = QRectF(x, y, bar_w, max(2.0, bar_h))
            self._bar_rects.append(bar_rect)
            p.drawRoundedRect(bar_rect, 5, 5)

            p.setPen(QColor(TEXT_SECONDARY))
            p.drawText(
                QRectF(x_center - 24, top + chart_h + 8, 48, 18),
                Qt.AlignmentFlag.AlignCenter,
                labels[i],
            )
            p.drawText(
                QRectF(x_center - 24, top + chart_h + 24, 48, 16),
                Qt.AlignmentFlag.AlignCenter,
                str(val),
            )

    def mouseMoveEvent(self, event):
        pos = event.position()
        for i, rect in enumerate(self._bar_rects):
            if rect.adjusted(-8, -8, 8, 8).contains(pos):
                d = self._start + timedelta(days=i)
                detail = self._details[i] if i < len(self._details) else Counter()
                if not detail:
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        f"{d:%m/%d (%a)}\n총 0개",
                        self,
                    )
                    return
                lines = [f"{d:%m/%d (%a)}", f"총 {self._counts[i]}개"]
                for name, cnt in detail.most_common(8):
                    lines.append(f"- {name}: {cnt}")
                QToolTip.showText(event.globalPosition().toPoint(), "\n".join(lines), self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)


class MonthlyHeatmapCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._year = date.today().year
        self._month = date.today().month
        self._counts: dict[int, int] = {}
        self._details: dict[int, Counter[str]] = {}
        self._cell_rects: dict[int, QRectF] = {}
        self.setMouseTracking(True)
        self.setMinimumHeight(300)

    def set_month(
        self,
        year: int,
        month: int,
        day_counts: dict[int, int],
        day_details: dict[int, Counter[str]] | None = None,
    ) -> None:
        self._year = year
        self._month = month
        self._counts = dict(day_counts)
        self._details = dict(day_details or {})
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        labels = ["월", "화", "수", "목", "금", "토", "일"]
        left = 12
        right = 12
        top = 34
        bottom = 10
        grid_w = max(1, w - left - right)
        grid_h = max(1, h - top - bottom)
        cell_w = grid_w / 7.0
        cell_h = grid_h / 6.0

        for i, d in enumerate(labels):
            p.setPen(QColor(TEXT_SECONDARY))
            p.drawText(QRectF(left + i * cell_w, 8, cell_w, 20), Qt.AlignmentFlag.AlignCenter, d)

        first_weekday, days_in_month = calendar.monthrange(self._year, self._month)  # Mon=0
        max_v = max(self._counts.values()) if self._counts else 1
        self._cell_rects = {}
        for day in range(1, days_in_month + 1):
            idx = first_weekday + (day - 1)
            row = idx // 7
            col = idx % 7
            x = left + col * cell_w + 2
            y = top + row * cell_h + 2
            cw = cell_w - 4
            ch = cell_h - 4
            self._cell_rects[day] = QRectF(x, y, cw, ch)

            v = self._counts.get(day, 0)
            intensity = (v / max_v) if max_v > 0 else 0
            # 0일은 거의 흰색, 많을수록 빨강 진하게
            color = QColor(
                255,
                int(248 - 130 * intensity),
                int(248 - 130 * intensity),
            )
            p.setPen(QPen(QColor("#ececec"), 1))
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y, cw, ch), 5, 5)

            p.setPen(QColor(TEXT_PRIMARY))
            p.drawText(QRectF(x + 6, y + 4, cw - 12, 16), Qt.AlignmentFlag.AlignLeft, str(day))
            if v > 0:
                p.setPen(QColor(TEXT_SECONDARY))
                p.drawText(QRectF(x, y, cw, ch), Qt.AlignmentFlag.AlignCenter, str(v))

    def mouseMoveEvent(self, event):
        pos = event.position()
        for day, rect in self._cell_rects.items():
            if rect.contains(pos):
                d = date(self._year, self._month, day)
                total = self._counts.get(day, 0)
                detail = self._details.get(day, Counter())
                if not detail:
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        f"{d:%Y-%m-%d}\n총 0개",
                        self,
                    )
                    return
                lines = [f"{d:%Y-%m-%d}", f"총 {total}개"]
                for name, cnt in detail.most_common(8):
                    lines.append(f"- {name}: {cnt}")
                QToolTip.showText(event.globalPosition().toPoint(), "\n".join(lines), self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)


class ExpirationStatsWidget(QWidget):
    """일/주/월 유통기한 통계."""

    MODE_DAILY = "daily"
    MODE_WEEKLY = "weekly"
    MODE_MONTHLY = "monthly"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logs: list[ExpLog] = []
        self._mode = self.MODE_DAILY
        self._anchor = date.today()

        self._daily_items: dict[date, Counter[str]] = defaultdict(Counter)
        self._daily_counts: Counter[date] = Counter()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.next_btn = QPushButton("▶")
        self.period_btn = QPushButton("")
        self.period_btn.setFlat(True)
        self.period_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.period_btn, 1)
        nav.addWidget(self.next_btn)
        root.addLayout(nav)

        tabs = QHBoxLayout()
        self.daily_btn = QPushButton("일별")
        self.weekly_btn = QPushButton("주별")
        self.monthly_btn = QPushButton("월별")
        for b in (self.daily_btn, self.weekly_btn, self.monthly_btn):
            b.setCheckable(True)
            tabs.addWidget(b)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.addButton(self.daily_btn)
        self.group.addButton(self.weekly_btn)
        self.group.addButton(self.monthly_btn)
        self.daily_btn.setChecked(True)
        root.addLayout(tabs)

        self.stack = QStackedWidget()
        self.daily_table = QTableWidget()
        self.daily_table.setColumnCount(2)
        self.daily_table.setHorizontalHeaderLabels(["품목명", "개수"])
        self.daily_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.daily_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.daily_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.daily_table.setAlternatingRowColors(False)
        self.daily_table.horizontalHeader().setStretchLastSection(False)
        self.daily_table.horizontalHeader().setSectionResizeMode(
            0, self.daily_table.horizontalHeader().ResizeMode.Stretch
        )
        self.daily_table.setColumnWidth(1, 80)

        self.weekly_canvas = WeeklyBarCanvas()
        self.monthly_canvas = MonthlyHeatmapCanvas()
        self.weekly_table = QTableWidget()
        self.weekly_table.setColumnCount(2)
        self.weekly_table.setHorizontalHeaderLabels(["해당 주 유통기한 임박 물품", "개수"])
        self.weekly_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.weekly_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.weekly_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.weekly_table.horizontalHeader().setStretchLastSection(False)
        self.weekly_table.horizontalHeader().setSectionResizeMode(
            0, self.weekly_table.horizontalHeader().ResizeMode.Stretch
        )
        self.weekly_table.setColumnWidth(1, 90)
        self.weekly_table.setMinimumHeight(140)
        self.weekly_table.setMaximumHeight(220)
        self.monthly_table = QTableWidget()
        self.monthly_table.setColumnCount(2)
        self.monthly_table.setHorizontalHeaderLabels(["해당 월 유통기한 임박 물품", "개수"])
        self.monthly_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.monthly_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.monthly_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.monthly_table.horizontalHeader().setStretchLastSection(False)
        self.monthly_table.horizontalHeader().setSectionResizeMode(
            0, self.monthly_table.horizontalHeader().ResizeMode.Stretch
        )
        self.monthly_table.setColumnWidth(1, 90)
        self.monthly_table.setMinimumHeight(140)
        self.monthly_table.setMaximumHeight(220)

        weekly_page = QWidget()
        weekly_layout = QVBoxLayout(weekly_page)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        weekly_layout.setSpacing(8)
        weekly_layout.addWidget(self.weekly_table)
        weekly_layout.addWidget(self.weekly_canvas, 1)
        monthly_page = QWidget()
        monthly_layout = QVBoxLayout(monthly_page)
        monthly_layout.setContentsMargins(0, 0, 0, 0)
        monthly_layout.setSpacing(8)
        monthly_layout.addWidget(self.monthly_table)
        monthly_layout.addWidget(self.monthly_canvas, 1)

        self.stack.addWidget(self.daily_table)
        self.stack.addWidget(weekly_page)
        self.stack.addWidget(monthly_page)
        root.addWidget(self.stack, 1)

        self.prev_btn.clicked.connect(lambda: self._shift_period(-1))
        self.next_btn.clicked.connect(lambda: self._shift_period(1))
        self.period_btn.clicked.connect(self._open_date_picker)
        self.daily_btn.clicked.connect(lambda: self._set_mode(self.MODE_DAILY))
        self.weekly_btn.clicked.connect(lambda: self._set_mode(self.MODE_WEEKLY))
        self.monthly_btn.clicked.connect(lambda: self._set_mode(self.MODE_MONTHLY))

        self._refresh()

    def set_logs(self, rows: list[dict]) -> None:
        logs: list[ExpLog] = []
        for r in rows:
            exp = (r.get("expiration_date") or "").strip()
            if not exp:
                continue
            try:
                d = datetime.fromisoformat(exp.replace("Z", "")).date()
            except ValueError:
                try:
                    d = datetime.strptime(exp[:10], "%Y-%m-%d").date()
                except Exception:
                    continue
            product_name = str(r.get("product_name") or "").strip()
            if not product_name:
                product_name = str(r.get("item_code") or "").strip() or "알 수 없음"
            logs.append(
                ExpLog(
                    exp_date=d,
                    product_name=product_name,
                )
            )

        self._logs = logs
        self._daily_items = defaultdict(Counter)
        self._daily_counts = Counter()
        for lg in self._logs:
            self._daily_items[lg.exp_date][lg.product_name] += 1
            self._daily_counts[lg.exp_date] += 1
        self._refresh()

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._refresh()

    def _shift_period(self, delta: int) -> None:
        if self._mode == self.MODE_DAILY:
            self._anchor += timedelta(days=delta)
        elif self._mode == self.MODE_WEEKLY:
            self._anchor += timedelta(days=7 * delta)
        else:
            y, m = self._anchor.year, self._anchor.month
            m += delta
            while m < 1:
                y -= 1
                m += 12
            while m > 12:
                y += 1
                m -= 12
            day = min(self._anchor.day, calendar.monthrange(y, m)[1])
            self._anchor = date(y, m, day)
        self._refresh()

    def _open_date_picker(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("날짜 선택")
        d.setStyleSheet(
            """
            QDialog { background: #ffffff; color: #222222; }
            QCalendarWidget QWidget { alternate-background-color: #ffffff; }
            QCalendarWidget QToolButton {
                color: #222222; background: #ffffff; border: 1px solid #dddddd; padding: 4px;
            }
            QCalendarWidget QMenu { color: #222222; background: #ffffff; }
            QCalendarWidget QSpinBox {
                color: #222222; background: #ffffff; selection-background-color: #e8dcc4;
            }
            QCalendarWidget QAbstractItemView:enabled {
                color: #222222;
                background: #ffffff;
                selection-background-color: #C4902B;
                selection-color: #ffffff;
            }
            """
        )
        lay = QVBoxLayout(d)
        cal = QCalendarWidget(d)
        cal.setGridVisible(False)
        cal.setSelectedDate(QDate(self._anchor.year, self._anchor.month, self._anchor.day))
        lay.addWidget(cal)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(buttons)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        if d.exec() == QDialog.DialogCode.Accepted:
            qd = cal.selectedDate()
            self._anchor = date(qd.year(), qd.month(), qd.day())
            self._refresh()

    def _refresh(self) -> None:
        if self._mode == self.MODE_DAILY:
            self.stack.setCurrentIndex(0)
            self.period_btn.setText(self._anchor.strftime("%Y. %m. %d"))
            items = self._daily_items.get(self._anchor, Counter())
            rows = sorted(items.items(), key=lambda x: x[0])
            self.daily_table.setRowCount(len(rows))
            for i, (name, cnt) in enumerate(rows):
                self.daily_table.setItem(i, 0, QTableWidgetItem(name))
                self.daily_table.setItem(i, 1, QTableWidgetItem(str(cnt)))
            return

        if self._mode == self.MODE_WEEKLY:
            self.stack.setCurrentIndex(1)
            start = self._anchor - timedelta(days=self._anchor.weekday())
            end = start + timedelta(days=6)
            self.period_btn.setText(f"{start:%Y. %m. %d} ~ {end:%m. %d}")
            counts = [self._daily_counts.get(start + timedelta(days=i), 0) for i in range(7)]
            details = [self._daily_items.get(start + timedelta(days=i), Counter()) for i in range(7)]
            self.weekly_canvas.set_week(start, counts, details)
            weekly_total = Counter()
            for d_counter in details:
                weekly_total.update(d_counter)
            rows = sorted(weekly_total.items(), key=lambda x: (-x[1], x[0]))
            self.weekly_table.setRowCount(len(rows))
            for i, (name, cnt) in enumerate(rows):
                self.weekly_table.setItem(i, 0, QTableWidgetItem(name))
                self.weekly_table.setItem(i, 1, QTableWidgetItem(str(cnt)))
            return

        self.stack.setCurrentIndex(2)
        y, m = self._anchor.year, self._anchor.month
        self.period_btn.setText(f"{y}. {m:02d}.")
        day_counts: dict[int, int] = {}
        day_details: dict[int, Counter[str]] = {}
        month_total = Counter()
        for d, cnt in self._daily_counts.items():
            if d.year == y and d.month == m:
                day_counts[d.day] = day_counts.get(d.day, 0) + cnt
                detail = self._daily_items.get(d, Counter())
                day_details[d.day] = detail
                month_total.update(detail)
        rows = sorted(month_total.items(), key=lambda x: (-x[1], x[0]))
        self.monthly_table.setRowCount(len(rows))
        for i, (name, cnt) in enumerate(rows):
            self.monthly_table.setItem(i, 0, QTableWidgetItem(name))
            self.monthly_table.setItem(i, 1, QTableWidgetItem(str(cnt)))
        self.monthly_canvas.set_month(y, m, day_counts, day_details)

