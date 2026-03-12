"""도넛 차트 위젯 — 비율 표시용 (창고별 재고 등)."""

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import QWidget

from theme import TEXT_SECONDARY, ACCENT, BG_MAIN


# 창고별 색상 (1L, 2L, 미분류)
CHART_COLORS = [
    QColor("#4A90D9"),   # 1L — 파랑
    QColor(ACCENT),      # 2L — 앰버(간장)
    QColor("#8B9DC3"),   # 미분류 — 회청
]


class DonutChartWidget(QWidget):
    """도넛 차트. data = [(label, value), ...] 형태."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, int]] = []
        self.setMinimumSize(280, 280)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

    def set_data(self, data: list[tuple[str, int]]) -> None:
        """[(inventory_name, current_qty), ...]"""
        self._data = [(str(label), int(v) if v >= 0 else 0) for label, v in data]
        self.update()

    def get_data(self) -> list[tuple[str, int]]:
        """현재 표시 중인 데이터 반환."""
        return list(self._data)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        side = min(w, h)
        margin = 50
        r = (side - margin * 2) / 2
        cx, cy = w / 2, h / 2

        total = sum(v for _, v in self._data)
        if total <= 0:
            # 빈 도넛
            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            painter.setPen(QPen(QColor(TEXT_SECONDARY), 2))
            painter.setBrush(QBrush(QColor(BG_MAIN)))
            painter.drawPie(rect, 0, 360 * 16)
            inner_r = r * 0.55
            inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
            painter.setBrush(QBrush(QColor(BG_MAIN)))
            painter.drawEllipse(inner_rect)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            font = QFont()
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(QRectF(cx - 40, cy - 10, 80, 20), Qt.AlignmentFlag.AlignCenter, "데이터 없음")
            return

        start_angle = 90  # 12시 방향부터 시계 반대 방향
        hole_ratio = 0.55  # 구멍 반지름 비율

        for i, (label, value) in enumerate(self._data):
            if value <= 0:
                continue
            span = 360 * 16 * value / total  # 1/16도 단위
            color = CHART_COLORS[i % len(CHART_COLORS)]
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color))
            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            painter.drawPie(rect, int(start_angle * 16), int(span))
            start_angle += 360 * value / total

        # 구멍 (도넛 모양)
        inner_r = r * hole_ratio
        inner_rect = QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(BG_MAIN)))
        painter.drawEllipse(inner_rect)

        # 중앙 총합
        painter.setPen(QPen(QColor(TEXT_SECONDARY)))
        font = QFont()
        font.setPointSize(14)
        font.setWeight(600)
        painter.setFont(font)
        painter.drawText(QRectF(cx - 50, cy - 18, 100, 24), Qt.AlignmentFlag.AlignCenter, str(total))
        font.setPointSize(10)
        font.setWeight(400)
        painter.setFont(font)
        painter.drawText(QRectF(cx - 50, cy + 2, 100, 20), Qt.AlignmentFlag.AlignCenter, "총 수량")

        # 범례 (우측)
        legend_x = cx + r + 15
        legend_y = cy - (len(self._data) * 24) / 2 + 12
        for i, (label, value) in enumerate(self._data):
            if value <= 0:
                continue
            pct = 100 * value / total if total > 0 else 0
            color = CHART_COLORS[i % len(CHART_COLORS)]
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(legend_x), int(legend_y + i * 24 - 6), 12, 12)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            painter.drawText(
                int(legend_x + 18),
                int(legend_y + i * 24 + 4),
                f"{label} {value} ({pct:.0f}%)",
            )
