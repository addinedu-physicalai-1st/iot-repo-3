"""작업현황 보드 위젯 (Jira 보드 스타일 3열 + 우측 2단)."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class _StatusListWidget(QListWidget):
    def __init__(
        self,
        status_key: str,
        *,
        drag_enabled: bool,
        drop_enabled: bool,
        on_status_drop: Callable[[int, str, str], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.status_key = status_key
        self._on_status_drop = on_status_drop
        self.setDragEnabled(drag_enabled)
        self.setAcceptDrops(drop_enabled)
        self.setDropIndicatorShown(drop_enabled)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        if drag_enabled and drop_enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        elif drag_enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        elif drop_enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        else:
            self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

    def startDrag(self, supportedActions) -> None:
        item = self.currentItem()
        if item is None:
            return
        if bool(item.data(Qt.ItemDataRole.UserRole + 1)):
            return
        super().startDrag(supportedActions)

    def dropEvent(self, event) -> None:
        src = event.source()
        if not isinstance(src, _StatusListWidget):
            event.ignore()
            return
        source_status = getattr(src, "status_key", None)
        allowed = {"PENDING", "DELIVERED"}
        # 교차 이동(PENDING <-> DELIVERED)만 허용
        if (
            self.status_key not in allowed
            or source_status not in allowed
            or source_status == self.status_key
        ):
            event.ignore()
            return
        drag_item = src.currentItem() if isinstance(src, QListWidget) else None
        order_id = (
            int(drag_item.data(Qt.ItemDataRole.UserRole + 4))
            if drag_item is not None and isinstance(drag_item.data(Qt.ItemDataRole.UserRole + 4), int)
            else None
        )
        super().dropEvent(event)
        if (
            event.isAccepted()
            and order_id is not None
            and isinstance(source_status, str)
            and source_status != self.status_key
            and self._on_status_drop is not None
        ):
            self._on_status_drop(order_id, source_status, self.status_key)


class _Column(QWidget):
    def __init__(
        self,
        title: str,
        parent=None,
        accent: str = "#4A90D9",
        *,
        status_key: str = "",
        drag_enabled: bool = False,
        drop_enabled: bool = False,
        on_status_drop: Callable[[int, str, str], None] | None = None,
    ):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        self.title = QLabel(title)
        f = self.title.font()
        f.setPointSize(12)
        f.setWeight(700)
        self.title.setFont(f)
        self.list = _StatusListWidget(
            status_key,
            drag_enabled=drag_enabled,
            drop_enabled=drop_enabled,
            on_status_drop=on_status_drop,
            parent=self,
        )
        self.list.setAlternatingRowColors(False)
        self.list.setMouseTracking(True)
        self.list.viewport().setMouseTracking(True)
        self.title.setStyleSheet(f"color:{accent};")
        self.list.setStyleSheet(
            """
            QListWidget {
                background: #ffffff;
                border: 1px solid #e5e2dc;
                border-radius: 10px;
                padding: 6px;
            }
            QListWidget::item {
                border: 1px solid #ece8e2;
                border-radius: 8px;
                margin: 4px 2px;
                padding: 8px 10px;
                background: #fbfaf8;
            }
            QListWidget::item:selected {
                color: #2d2d2d;
                background: #eef3fb;
                border: 1px solid #d9e3f3;
            }
            """
        )
        root.addWidget(self.title)
        root.addWidget(self.list, 1)


class WorkStatusBoardWidget(QWidget):
    """
    주문 상태 보드:
    - 좌: PENDING
    - 중: DELIVERED(도착했지만 미완료)
    - 우: COMPLETED 또는 ERROR
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(900, 520)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        root = QHBoxLayout()
        root.setSpacing(12)

        self._status_change_handler: Callable[[int, str, str], bool] | None = None
        self.col_pending = _Column(
            "PENDING",
            self,
            "#8f98a3",
            status_key="PENDING",
            drag_enabled=True,
            drop_enabled=True,
            on_status_drop=self._on_status_drop,
        )
        self.col_delivered = _Column(
            "DELIVERED",
            self,
            "#4A90D9",
            status_key="DELIVERED",
            drag_enabled=True,
            drop_enabled=True,
            on_status_drop=self._on_status_drop,
        )
        self.col_completed = _Column("완료", self, "#2e8b57", status_key="COMPLETED")
        self.col_error = _Column("에러", self, "#c85656", status_key="ERROR")
        self._next_item_id: int = 1

        for col in (self.col_pending, self.col_delivered):
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            fr = QVBoxLayout(frame)
            fr.setContentsMargins(8, 8, 8, 8)
            fr.addWidget(col)
            frame.setStyleSheet(
                """
                QFrame {
                    background: #f8f6f2;
                    border: 1px solid #e8e4dc;
                    border-radius: 12px;
                }
                """
            )
            root.addWidget(frame, 1)

        # 우측: 완료/에러 수직 2칸 (비율 2:1)
        right = QFrame()
        right.setFrameShape(QFrame.Shape.StyledPanel)
        right.setStyleSheet(
            """
            QFrame {
                background: #f8f6f2;
                border: 1px solid #e8e4dc;
                border-radius: 12px;
            }
            """
        )
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.setSpacing(8)
        rv.addWidget(self.col_completed, 2)
        rv.addWidget(self.col_error, 1)
        root.addWidget(right, 1)
        outer.addLayout(root, 1)

        # 툴팁이 안 보이는 환경을 대비해 클릭 시 상세 팝업 제공
        self.col_pending.list.itemClicked.connect(self._on_item_clicked)
        self.col_delivered.list.itemClicked.connect(self._on_item_clicked)
        self.col_completed.list.itemClicked.connect(self._on_item_clicked)
        self.col_error.list.itemClicked.connect(self._on_item_clicked)

    def set_source_data(
        self, orders: list[dict], processes: list[dict], logs: list[dict]
    ) -> None:
        self._next_item_id = 1
        self.col_pending.list.clear()
        self.col_delivered.list.clear()
        self.col_completed.list.clear()
        self.col_error.list.clear()

        process_by_order: dict[int, list[dict]] = defaultdict(list)
        for p in processes or []:
            oid = p.get("order_id")
            if isinstance(oid, int):
                process_by_order[oid].append(p)

        error_by_process: dict[int, bool] = defaultdict(bool)
        # process_id -> 전체 로그 행
        logs_by_process: dict[int, list[dict]] = defaultdict(list)
        for lg in logs or []:
            pid = lg.get("process_id")
            if isinstance(pid, int):
                logs_by_process[pid].append(lg)
                if bool(lg.get("is_error")):
                    error_by_process[pid] = True

        for o in orders or []:
            oid = o.get("order_id")
            if not isinstance(oid, int):
                continue
            status = str(o.get("status") or "").upper()
            plist = process_by_order.get(oid, [])
            pids = [
                int(p.get("process_id"))
                for p in plist
                if isinstance(p.get("process_id"), int)
            ]

            completed = any(str(p.get("status") or "").upper() == "COMPLETED" for p in plist)
            has_error = any(error_by_process.get(int(p.get("process_id")), False) for p in plist if p.get("process_id") is not None)
            show_order_log_ids = bool(completed or has_error)
            tooltip = self._build_order_tooltip(
                o,
                pids,
                logs_by_process,
                has_error,
                show_order_log_ids=show_order_log_ids,
            )

            if status != "DELIVERED":
                self._append(self.col_pending.list, f"Order #{oid}", tooltip, order_id=oid)
                continue

            if has_error:
                self._append(self.col_error.list, f"Order #{oid}", tooltip, order_id=oid)
            elif completed:
                self._append(self.col_completed.list, f"Order #{oid}", tooltip, order_id=oid)
            else:
                self._append(self.col_delivered.list, f"Order #{oid}", tooltip, order_id=oid)

    def set_status_change_handler(self, handler: Callable[[int, str, str], bool] | None) -> None:
        self._status_change_handler = handler

    def _append(
        self, lw: QListWidget, text: str, tooltip: str = "", *, order_id: int | None = None
    ) -> None:
        item = QListWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if tooltip:
            item.setToolTip(tooltip)
            item.setData(Qt.ItemDataRole.UserRole, tooltip)
        item.setData(Qt.ItemDataRole.UserRole + 1, False)  # detail row 여부
        item.setData(Qt.ItemDataRole.UserRole + 2, self._next_item_id)  # base item id
        if isinstance(order_id, int):
            item.setData(Qt.ItemDataRole.UserRole + 4, order_id)
        self._next_item_id += 1
        lw.addItem(item)

    def _on_status_drop(self, order_id: int, from_status: str, to_status: str) -> None:
        self._remove_detail_rows_for_order(self.col_pending.list, order_id)
        self._remove_detail_rows_for_order(self.col_delivered.list, order_id)
        if self._status_change_handler is None:
            return
        self._status_change_handler(order_id, from_status, to_status)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        lw = self.sender()
        if not isinstance(lw, QListWidget):
            return
        if bool(item.data(Qt.ItemDataRole.UserRole + 1)):
            return

        base_id = item.data(Qt.ItemDataRole.UserRole + 2)
        if not isinstance(base_id, int):
            return

        row = lw.row(item)
        detail_row = self._find_detail_row(lw, base_id)
        # 같은 항목 재클릭 시에만 접기 (다른 상세는 유지)
        if detail_row is not None:
            lw.takeItem(detail_row)
            lw.clearSelection()
            return

        detail = str(item.data(Qt.ItemDataRole.UserRole) or item.toolTip() or "").strip()
        if not detail:
            return

        # 빈 줄을 보존해서 "주문 물품"과 "에러 물품" 섹션을 시각적으로 분리
        lines = detail.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        # 첫 줄(Order #id)은 이미 카드 제목으로 보이므로 상세 블럭에서는 제거
        if lines and lines[0].strip().lower() == item.text().strip().lower():
            lines = lines[1:]
        if not lines:
            return

        insert_row = row + 1
        d_item = QListWidgetItem("\n".join(lines))
        d_item.setData(Qt.ItemDataRole.UserRole + 1, True)
        d_item.setData(Qt.ItemDataRole.UserRole + 3, base_id)  # parent base id
        d_item.setData(Qt.ItemDataRole.UserRole + 4, item.data(Qt.ItemDataRole.UserRole + 4))
        d_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        # 상세는 글씨를 살짝 작게
        f = QFont()
        f.setPointSize(10)
        d_item.setData(Qt.ItemDataRole.FontRole, f)
        # 상세 블럭은 가독성을 위해 회색 톤
        d_item.setData(Qt.ItemDataRole.ForegroundRole, Qt.GlobalColor.darkGray)
        # 높이 충분히 확보
        sz = d_item.sizeHint()
        sz.setHeight(max(88, sz.height() * 2))
        d_item.setSizeHint(sz)
        lw.insertItem(insert_row, d_item)
        lw.clearSelection()

    def _find_detail_row(self, lw: QListWidget, base_id: int) -> int | None:
        for i in range(lw.count()):
            it = lw.item(i)
            if not bool(it.data(Qt.ItemDataRole.UserRole + 1)):
                continue
            if it.data(Qt.ItemDataRole.UserRole + 3) == base_id:
                return i
        return None

    def _remove_detail_rows_for_order(self, lw: QListWidget, order_id: int) -> None:
        for i in range(lw.count() - 1, -1, -1):
            it = lw.item(i)
            if not bool(it.data(Qt.ItemDataRole.UserRole + 1)):
                continue
            if it.data(Qt.ItemDataRole.UserRole + 4) == order_id:
                lw.takeItem(i)

    def _build_order_tooltip(
        self,
        order: dict,
        process_ids: list[int],
        logs_by_process: dict[int, list[dict]],
        has_error: bool,
        *,
        show_order_log_ids: bool,
    ) -> str:
        lines: list[str] = [f"Order #{order.get('order_id')}"]
        items = order.get("items") or []
        # 주문 물품 합산
        order_items_agg: dict[str, int] = defaultdict(int)
        for it in items:
            name = str(it.get("product_name") or it.get("item_code") or "알 수 없음").strip()
            qty = int(it.get("expected_qty") or 0)
            order_items_agg[name] += qty

        # 주문 물품별 로그ID 집계 (에러/정상 모두)
        item_log_ids: dict[str, set[int]] = defaultdict(set)
        for pid in process_ids:
            for lg in logs_by_process.get(pid, []):
                name = str(lg.get("product_name") or lg.get("item_code") or "알 수 없음").strip()
                lid = lg.get("log_id")
                if isinstance(lid, int):
                    item_log_ids[name].add(lid)

        if items:
            lines.append("주문 물품")
            for name, qty in sorted(order_items_agg.items(), key=lambda x: (-x[1], x[0])):
                lines.append(f"- {name}: {qty}개")
                if show_order_log_ids:
                    ids = sorted(item_log_ids.get(name, set()))
                    ids_text = ", ".join(str(i) for i in ids[:10])
                    if len(ids) > 10:
                        ids_text += ", ..."
                    lines.append(f"  로그ID: {ids_text if ids_text else '없음'}")
        else:
            lines.append("주문 물품: 없음")

        if has_error:
            # 에러 물품은 절대 합산하지 않고 로그 단위로 표기
            error_entries: list[tuple[int | None, str]] = []
            for pid in process_ids:
                for lg in logs_by_process.get(pid, []):
                    if not bool(lg.get("is_error")):
                        continue
                    lid = lg.get("log_id")
                    name = str(lg.get("product_name") or lg.get("item_code") or "알 수 없음").strip()
                    error_entries.append((int(lid) if isinstance(lid, int) else None, name))
            lines.append("")
            lines.append("에러 물품 (로그 단위)")
            if error_entries:
                error_entries.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else 10**9))
                for idx, (lid, name) in enumerate(error_entries):
                    lines.append(f"- {name}")
                    lines.append(f"  로그ID: {lid if lid is not None else '없음'}")
                    if idx < len(error_entries) - 1:
                        lines.append("")
            else:
                lines.append("- 에러 상세 없음")
        return "\n".join(lines)

