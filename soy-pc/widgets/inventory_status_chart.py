"""재고 현황 위젯 — 상단 반원 도넛 + 하단 브랜드별 막대."""

import math

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PyQt6.QtWidgets import QWidget

from theme import TEXT_SECONDARY, ACCENT

# 부채꼴·막대 색상 (1L, 2L, 미분류)
COLOR_1L = QColor("#4A90D9")
COLOR_2L = QColor(ACCENT)
COLOR_MI = QColor("#8B9DC3")
COLOR_JIN = QColor("#D4734A")
COLOR_GUK = QColor("#2E7D6E")


class InventoryStatusChartWidget(QWidget):
    """
    재고 현황: 상단 부채꼴(1L, 2L, 미분류) + 하단 왼쪽 몽고 / 오른쪽 샘표 막대 차트.
    X축: 1L, 2L, 미분류. 1L·2L은 진+국 합산, 각각 다른 색.
    data = [{brand, category, inventory_id, count}, ...]
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
        self._arc_totals: dict[int, int] = {1: 0, 2: 0, 3: 0}
        self._category_totals: dict[str, int] = {"jin": 0, "guk": 0}
        self._split_by_category = False
        self.setMinimumSize(900, 860)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

    def set_data(self, data: list[dict]) -> None:
        """API 응답: [{brand, category, inventory_id, count}, ...]"""
        self._data = list(data)
        self._arc_totals = {1: 0, 2: 0, 3: 0}
        self._category_totals = {"jin": 0, "guk": 0}
        for row in self._data:
            inv_id = row.get("inventory_id")
            count = int(row.get("count") or 0)
            if inv_id in (1, 2, 3):
                self._arc_totals[inv_id] = self._arc_totals.get(inv_id, 0) + count
            category = str(row.get("category") or "")
            if "진" in category:
                self._category_totals["jin"] += count
            elif "국" in category:
                self._category_totals["guk"] += count
        self.update()

    def set_split_by_category(self, enabled: bool) -> None:
        """하단 막대: 합산(False) / 진·국 분리 누적(True)."""
        self._split_by_category = bool(enabled)
        self.update()

    def _get_brand_totals(self, brand: str) -> dict[int, int]:
        """브랜드별 inventory_id 합계 (진+국 합침)."""
        out = {1: 0, 2: 0, 3: 0}
        for r in self._data:
            if r.get("brand") != brand:
                continue
            inv_id = r.get("inventory_id")
            if inv_id in (1, 2, 3):
                out[inv_id] = out.get(inv_id, 0) + (r.get("count") or 0)
        return out

    def _get_brand_split_totals(self, brand: str) -> dict[int, dict[str, int]]:
        """브랜드별 inventory_id × category(진/국) 합계."""
        out = {
            1: {"jin": 0, "guk": 0},
            2: {"jin": 0, "guk": 0},
            3: {"jin": 0, "guk": 0},
        }
        for r in self._data:
            if r.get("brand") != brand:
                continue
            inv_id = r.get("inventory_id")
            if inv_id not in (1, 2, 3):
                continue
            category = str(r.get("category") or "")
            count = int(r.get("count") or 0)
            if "진" in category:
                out[inv_id]["jin"] += count
            elif "국" in category:
                out[inv_id]["guk"] += count
        return out

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        # 제목
        font_title = QFont()
        font_title.setPointSize(16)
        font_title.setWeight(700)
        painter.setFont(font_title)
        painter.setPen(QColor(TEXT_SECONDARY))
        painter.drawText(0, 28, "1. 재고 현황")

        # 상단 반원 도넛
        pie_cy = 360
        pie_r = 300
        self._draw_pie(painter, w / 2, pie_cy, pie_r)

        # 하단: 토글 상태에 따른 단일 막대 섹션
        bar_y = 600
        bar_h = 140
        half_w = w / 2
        center_gap = 12
        self._draw_bar_chart(
            painter, 0, half_w - center_gap, bar_y, bar_h, "몽고", split=self._split_by_category
        )
        self._draw_bar_chart(
            painter, half_w + center_gap, w, bar_y, bar_h, "샘표", split=self._split_by_category
        )

    def _draw_pie(self, painter: QPainter, cx: float, cy: float, r: float) -> None:
        """반원 도넛 차트. 1L, 2L, 미분류 비율로 180도 링을 분할."""
        if self._split_by_category:
            labels = [
                ("jin", "진간장", COLOR_JIN, self._category_totals.get("jin", 0)),
                ("guk", "국간장", COLOR_GUK, self._category_totals.get("guk", 0)),
            ]
        else:
            labels = [
                (1, "1L", COLOR_1L, self._arc_totals.get(1, 0)),
                (2, "2L", COLOR_2L, self._arc_totals.get(2, 0)),
                (3, "미분류", COLOR_MI, self._arc_totals.get(3, 0)),
            ]
        total = sum(v for _, _, _, v in labels)
        ring_w = max(18, int(r * 0.42))
        arc_r = r - (ring_w / 2)
        arc_rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)

        # 반원 도넛: 9시 -> 3시 (12시 경유), 즉 위쪽 180도
        # Qt에서 음수 span은 시계방향이므로, 9시에서 -180도로 그리면 위쪽 반원이 된다.
        start_deg = 180
        span_total_deg = 180

        if total <= 0:
            pen = QPen(
                QColor("#c5c5c5"),
                ring_w,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.FlatCap,
            )
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(arc_rect, start_deg * 16, -span_total_deg * 16)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            font = QFont()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(
                QRectF(cx - 50, cy - 10, 100, 20),
                Qt.AlignmentFlag.AlignCenter,
                "데이터 없음",
            )
            return

        font_pct = QFont()
        font_pct.setPointSize(12)
        font_pct.setWeight(600)

        start = start_deg
        for _key, label, color, val in labels:
            if val <= 0:
                continue
            span_deg = -(span_total_deg * val / total)
            pen = QPen(color, ring_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(arc_rect, int(start * 16), int(span_deg * 16))

            # 조각 위 비율 텍스트
            mid_deg = start + (span_deg / 2.0)
            theta = math.radians(mid_deg)
            # 조각 두께의 정중앙 반경에 퍼센트 배치
            text_r = arc_r
            tx = cx + (text_r * math.cos(theta))
            ty = cy - (text_r * math.sin(theta))
            pct = round(100 * val / total)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            painter.setFont(font_pct)
            painter.drawText(
                QRectF(tx - 22, ty - 12, 44, 24),
                Qt.AlignmentFlag.AlignCenter,
                f"{pct}%",
            )
            start += span_deg

        # 반원 중앙에 총 재고 수량 표시
        font_total_num = QFont()
        font_total_num.setPointSize(20)
        font_total_num.setWeight(700)
        painter.setFont(font_total_num)
        painter.setPen(QPen(QColor(TEXT_SECONDARY)))
        painter.drawText(
            QRectF(cx - 90, cy - r * 0.46, 180, 38),
            Qt.AlignmentFlag.AlignCenter,
            str(total),
        )

        font_total_label = QFont()
        font_total_label.setPointSize(11)
        font_total_label.setWeight(500)
        painter.setFont(font_total_label)
        painter.drawText(
            QRectF(cx - 90, cy - r * 0.34, 180, 24),
            Qt.AlignmentFlag.AlignCenter,
            "총 재고 수량",
        )

        # 범례 (반원 호 아래) - 3열 고정 배치로 겹침 방지
        legend_y = cy + 30
        font = QFont()
        font.setPointSize(11)
        painter.setFont(font)
        n = max(1, len(labels))
        col_w = 220 if n == 3 else 260
        legend_start_x = cx - (col_w * n / 2.0)
        for idx, (_key, label, color, val) in enumerate(labels):
            col_x = legend_start_x + (idx * col_w)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(col_x + 8), int(legend_y - 6), 12, 12)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            pct = round(100 * val / total) if total > 0 else 0
            painter.drawText(
                QRectF(col_x + 26, legend_y - 12, col_w - 20, 24),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{label} {val} ({pct}%)",
            )

    def _draw_bar_chart(
        self,
        painter: QPainter,
        left: float,
        right: float,
        top_y: float,
        bar_height: float,
        brand: str,
        *,
        split: bool,
    ) -> None:
        """브랜드별 막대: X축 1L, 2L, 미분류. 각 슬롯 합산, 색상 구분."""
        chart_w = right - left
        font = QFont()
        font.setPointSize(13)
        font.setWeight(600)
        painter.setFont(font)
        painter.setPen(QColor(TEXT_SECONDARY))
        painter.drawText(int(left + 10), int(top_y - 8), brand)

        slots = [(1, "1L", COLOR_1L), (2, "2L", COLOR_2L), (3, "미분류", COLOR_MI)]
        # 막대 사이 간격을 약 1cm 수준으로 고정
        bar_w = 42
        gap_w = 38
        cluster_w = (bar_w * 3) + (gap_w * 2)
        group_left = left + (chart_w - cluster_w) / 2
        bar_max_h = bar_height - 50
        split_totals = self._get_brand_split_totals(brand)
        totals = self._get_brand_totals(brand)
        max_val = max(totals.values()) or 1

        for i, (inv_id, slot_label, color) in enumerate(slots):
            x = group_left + i * (bar_w + gap_w)
            base_y = top_y + bar_height - 38

            # X축 라벨
            font.setPointSize(10)
            font.setWeight(400)
            painter.setFont(font)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            label_rect = QRectF(
                x - 22,
                int(top_y + bar_height - 32),
                bar_w + 44,
                62,
            )

            if split:
                # 진/국 분리 누적 막대
                jin_val = split_totals[inv_id]["jin"]
                guk_val = split_totals[inv_id]["guk"]
                total_val = jin_val + guk_val
                if max_val > 0 and total_val > 0:
                    jin_h = bar_max_h * jin_val / max_val
                    guk_h = bar_max_h * guk_val / max_val
                    if jin_h > 0:
                        rect_j = QRectF(x, base_y - jin_h, bar_w, jin_h)
                        painter.setBrush(QBrush(COLOR_JIN))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawRect(rect_j)
                    if guk_h > 0:
                        rect_g = QRectF(x, base_y - jin_h - guk_h, bar_w, guk_h)
                        painter.setBrush(QBrush(COLOR_GUK))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawRect(rect_g)
                    # 슬롯별 총량 외곽선
                    total_h = max(6, bar_max_h * total_val / max_val)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(color, 1))
                    painter.drawRoundedRect(QRectF(x, base_y - total_h, bar_w, total_h), 4, 4)
                painter.setPen(QPen(QColor(TEXT_SECONDARY)))
                painter.drawText(
                    label_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    f"{slot_label}\n진간장: {jin_val}\n국간장: {guk_val}",
                )
            else:
                # 합산 막대 (1L/2L/미분류 각각 다른 색)
                val = totals.get(inv_id, 0)
                if max_val > 0 and val > 0:
                    h = max(6, bar_max_h * val / max_val)
                    rect = QRectF(x, base_y - h, bar_w, h)
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(rect, 6, 6)
                painter.setPen(QPen(QColor(TEXT_SECONDARY)))
                painter.drawText(
                    label_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    f"{slot_label}\n{val}",
                )

        if split:
            # 분리 모드 범례 (브랜드 영역 우측 상단)
            lx = right - 92
            ly = top_y - 18
            font.setPointSize(10)
            painter.setFont(font)
            painter.setBrush(QBrush(COLOR_JIN))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(lx), int(ly), 10, 10)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            painter.drawText(int(lx + 14), int(ly + 10), "진")
            painter.setBrush(QBrush(COLOR_GUK))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(lx + 38), int(ly), 10, 10)
            painter.setPen(QPen(QColor(TEXT_SECONDARY)))
            painter.drawText(int(lx + 52), int(ly + 10), "국")
