"""작업자 화면 — 메뉴 라우팅, 입고/분류/창고 페이지 조립."""

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QTableWidgetItem

from api import list_orders
from features.worker.inbound_dialog import InboundScanDialog
from features.worker.classify_page import setup_classify_page

logger = logging.getLogger(__name__)


def setup_worker_screen(window, stacked) -> None:
    """작업자 화면: 사이드바(주문 관리 메뉴), 주문 관리 페이지(송장 QR → 주문 delivered)."""
    worker = window.page_worker

    def back_to_lock():
        stacked.setCurrentIndex(0)

    worker.backButton.clicked.connect(back_to_lock)

    # 기본 페이지: 환영 화면(page_welcome)
    stack = worker.worker_content_stack
    stack.setCurrentIndex(0)

    # .ui 로더가 contentsMargins 4값을 처리하지 못하므로 Python에서 설정
    welcome_page = stack.widget(0)
    if welcome_page.layout():
        welcome_page.layout().setContentsMargins(32, 32, 32, 32)
    warehouse_page = stack.widget(4)
    if warehouse_page.layout():
        warehouse_page.layout().setContentsMargins(32, 32, 32, 32)
    card = worker.findChild(QFrame, "welcome_card")
    if card and card.layout():
        card.layout().setContentsMargins(40, 40, 40, 40)

    # ── 분류 페이지 세팅 ─────────────────────────────────────────
    (
        _controller,
        _refresh_classify_list,
        _refresh_warehouse_chart,
        _restore_classify_monitor,
        _stop_udp_camera,
    ) = setup_classify_page(worker, window, stacked, stack)

    # ── 메뉴 클릭 핸들러 ─────────────────────────────────────────
    def on_menu_inbound_clicked():
        if worker.menu_inbound.isChecked():
            worker.menu_classify.setChecked(False)
            worker.menu_warehouse.setChecked(False)
            stack.setCurrentIndex(1)  # page_inbound
        else:
            stack.setCurrentIndex(0)

    def on_menu_classify_clicked():
        if worker.menu_classify.isChecked():
            worker.menu_inbound.setChecked(False)
            worker.menu_warehouse.setChecked(False)
            stack.setCurrentIndex(3)  # page_classify
            _refresh_classify_list()
            _restore_classify_monitor()
        else:
            stack.setCurrentIndex(0)

    PAGE_WAREHOUSE = 4

    def on_menu_warehouse_clicked():
        if worker.menu_warehouse.isChecked():
            worker.menu_inbound.setChecked(False)
            worker.menu_classify.setChecked(False)
            stack.setCurrentIndex(PAGE_WAREHOUSE)
            _refresh_warehouse_chart()
        else:
            stack.setCurrentIndex(0)

    worker.menu_inbound.clicked.connect(on_menu_inbound_clicked)
    worker.menu_classify.clicked.connect(on_menu_classify_clicked)
    worker.menu_warehouse.clicked.connect(on_menu_warehouse_clicked)

    # ═══════════════════════════════════════════════════════════════
    # ═══ 주문 관리 (입고) 페이지 ═══════════════════════════════════
    # ═══════════════════════════════════════════════════════════════
    _inbound_orders_list: list[dict] = []

    def _qty_by_capacity(items: list[dict], capacity: str) -> int:
        cap_upper = (capacity or "").strip().upper()
        total = 0
        for it in items:
            qty = it.get("expected_qty", 0) or 0
            item_cap = (it.get("capacity") or "").strip().upper()
            if item_cap and item_cap == cap_upper:
                total += qty
                continue
            code = (it.get("item_code") or "").strip().upper()
            if code.endswith("_1L") and cap_upper == "1L":
                total += qty
            elif code.endswith("_2L") and cap_upper == "2L":
                total += qty
        return total

    def _refresh_inbound_order_list():
        nonlocal _inbound_orders_list
        try:
            _inbound_orders_list = list_orders()
        except (TimeoutError, RuntimeError, OSError, ConnectionError):
            _inbound_orders_list = []
            worker.orderTable.setRowCount(0)
            worker.orderTable.setHorizontalHeaderLabels(
                ["주문 ID", "주문일", "입고 여부", "1L", "2L"]
            )
            return
        worker.orderTable.setHorizontalHeaderLabels(
            ["주문 ID", "주문일", "입고 여부", "1L", "2L"]
        )
        worker.orderTable.setRowCount(0)
        flags_ro = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        for o in _inbound_orders_list:
            row = worker.orderTable.rowCount()
            worker.orderTable.insertRow(row)
            oid = o.get("order_id")
            date_str = (o.get("order_date") or "")[:10]
            status = (o.get("status") or "").strip().upper()
            입고_str = "입고됨" if status == "DELIVERED" else "대기"
            items = o.get("items") or []
            qty_1l = _qty_by_capacity(items, "1L")
            qty_2l = _qty_by_capacity(items, "2L")
            worker.orderTable.setItem(row, 0, QTableWidgetItem(str(oid)))
            worker.orderTable.item(row, 0).setData(Qt.ItemDataRole.UserRole, oid)
            worker.orderTable.setItem(row, 1, QTableWidgetItem(date_str))
            worker.orderTable.setItem(row, 2, QTableWidgetItem(입고_str))
            worker.orderTable.setItem(row, 3, QTableWidgetItem(str(qty_1l)))
            worker.orderTable.setItem(row, 4, QTableWidgetItem(str(qty_2l)))
            for c in range(5):
                worker.orderTable.item(row, c).setFlags(flags_ro)
        worker.orderTable.setColumnWidth(0, 72)
        worker.orderTable.setColumnWidth(1, 150)
        worker.orderTable.setColumnWidth(2, 100)
        worker.orderTable.setColumnWidth(3, 44)
        worker.orderTable.setColumnWidth(4, 44)

    # 주문 관리 클릭 시 목록 갱신
    def _on_menu_inbound_clicked_extra():
        on_menu_inbound_clicked()
        _refresh_inbound_order_list()

    worker.menu_inbound.clicked.disconnect(on_menu_inbound_clicked)
    worker.menu_inbound.clicked.connect(_on_menu_inbound_clicked_extra)

    # 입고 스캔 버튼
    def on_inbound_scan_button():
        dialog = InboundScanDialog(
            parent=window,
            on_order_delivered=_refresh_inbound_order_list,
        )
        dialog.exec()
        _refresh_inbound_order_list()

    worker.inboundScanButton.clicked.connect(on_inbound_scan_button)

    # 주문 상세 페이지
    PAGE_ORDER_DETAIL = 2

    def on_order_row_clicked(row: int, _column: int):
        if row < 0:
            return
        item0 = worker.orderTable.item(row, 0)
        oid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        if oid is None:
            return
        order = next(
            (o for o in _inbound_orders_list if o.get("order_id") == oid), None
        )
        if not order:
            return
        worker.label_order_detail_title.setText(f"주문 상세 # {oid}")
        worker.orderDetailTable.setHorizontalHeaderLabels(
            ["품목명", "품목 코드", "수량"]
        )
        worker.orderDetailTable.setRowCount(0)
        flags_ro = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        for it in order.get("items") or []:
            product_name = it.get("product_name") or it.get("item_code") or "—"
            code = it.get("item_code") or ""
            r = worker.orderDetailTable.rowCount()
            worker.orderDetailTable.insertRow(r)
            worker.orderDetailTable.setItem(r, 0, QTableWidgetItem(product_name))
            worker.orderDetailTable.setItem(r, 1, QTableWidgetItem(code))
            worker.orderDetailTable.setItem(
                r, 2, QTableWidgetItem(str(it.get("expected_qty", 0)))
            )
            for c in range(3):
                worker.orderDetailTable.item(r, c).setFlags(flags_ro)
        worker.orderDetailTable.setColumnWidth(0, 180)
        worker.orderDetailTable.setColumnWidth(1, 90)
        stack.setCurrentIndex(PAGE_ORDER_DETAIL)

    worker.orderTable.cellDoubleClicked.connect(on_order_row_clicked)

    def on_order_detail_back():
        stack.setCurrentIndex(1)

    worker.orderDetailBackButton.clicked.connect(on_order_detail_back)

    # ── 화면 전환 시 카메라 정리 ─────────────────────────────────
    def _on_page_leaving():
        _stop_udp_camera()

    def _on_stack_changed(index: int):
        if index != 3:
            _stop_udp_camera()
        else:
            _restore_classify_monitor()

    stacked.currentChanged.connect(lambda _: _on_page_leaving())
    stack.currentChanged.connect(_on_stack_changed)
