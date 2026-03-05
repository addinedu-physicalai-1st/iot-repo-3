"""관리자 화면 — 사이드바 메뉴, 작업자 관리(목록·CRUD). soy-server TCP 연동."""
import os
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDialog, QTableWidgetItem

from qfluentwidgets import MessageBox

from api import (
    WorkerCreateConflict,
    WorkerNotFound,
    create_worker as api_create_worker,
    delete_worker as api_delete_worker,
    get_first_admin_id,
    list_access_logs,
    list_inventory,
    list_inventory_status_stats,
    list_item_sorting_logs,
    list_orders,
    list_processes,
    list_workers,
    order_mark_delivered,
    order_set_status,
    update_worker as api_update_worker,
)
from PyQt6.QtWidgets import QFileDialog

from api.client import admin_logout, set_card_read_callback
from serial_rfid import SerialRFIDReader, get_register_serial_port
from widgets.donut_chart import DonutChartWidget
from widgets.expiration_stats_widget import ExpirationStatsWidget
from widgets.inventory_status_chart import InventoryStatusChartWidget
from widgets.work_status_board_widget import WorkStatusBoardWidget

_USE_SERVER_RFID = os.environ.get("SOY_USE_SERVER_RFID", "1").strip().lower() not in ("0", "false", "no")


class _CardReadBridge(QObject):
    """서버 TCP reader 스레드 → 메인 스레드로 UID 전달 (시그널은 스레드 안전)."""
    card_uid_received = pyqtSignal(str)


def _open_worker_info_dialog(
    parent,
    ui_dir: str,
    worker_id: int,
    name: str,
    card_uid: str,
    created_at_str: str,
    refresh_table_callback,
) -> None:
    """작업자 정보 팝업. 수정/삭제 시 API 호출 후 테이블 갱신."""
    dialog = QDialog(parent)
    uic.loadUi(os.path.join(ui_dir, "worker_info_dialog.ui"), dialog)
    dialog._worker_id = worker_id
    dialog._refresh = refresh_table_callback

    def set_labels(n: str, u: str, date_str: str):
        dialog.label_name_value.setText(n or "—")
        dialog.label_uid_value.setText(u or "—")
        dialog.label_note_value.setText(date_str or "—")

    set_labels(name, card_uid, created_at_str)

    def do_edit():
        edit_d = QDialog(parent)
        uic.loadUi(os.path.join(ui_dir, "worker_edit_dialog.ui"), edit_d)
        edit_d.nameEdit.setText(name)
        edit_d.setWindowTitle("작업자 수정")

        def on_edit_ok():
            QGuiApplication.inputMethod().commit()
            new_name = edit_d.nameEdit.text().strip()
            if not new_name:
                box = MessageBox("입력 오류", "이름을 입력하세요.", edit_d)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                return
            try:
                api_update_worker(worker_id, name=new_name)
            except WorkerNotFound:
                box = MessageBox("수정 실패", "작업자를 찾을 수 없습니다.", edit_d)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                edit_d.reject()
                return
            except (TimeoutError, RuntimeError, OSError, ConnectionError) as e:
                box = MessageBox("수정 실패", f"서버 통신 오류:\n{e!s}", edit_d)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                return
            refresh_table_callback()
            set_labels(new_name, card_uid, created_at_str)
            edit_d.accept()

        edit_d.button_ok.clicked.connect(on_edit_ok)
        edit_d.button_cancel.clicked.connect(edit_d.reject)
        edit_d.nameEdit.returnPressed.connect(on_edit_ok)
        edit_d.exec()

    def do_delete():
        box = MessageBox(
            "삭제 확인",
            "이 작업자를 삭제하시겠습니까?",
            dialog,
        )
        if box.exec() != 1:  # Yes
            return
        try:
            api_delete_worker(worker_id)
        except WorkerNotFound:
            box2 = MessageBox("삭제 실패", "작업자를 찾을 수 없습니다.", dialog)
            box2.cancelButton.hide()
            box2.yesButton.setText("확인")
            box2.exec()
            return
        except (TimeoutError, RuntimeError, OSError, ConnectionError) as e:
            box2 = MessageBox("삭제 실패", f"서버 통신 오류:\n{e!s}", dialog)
            box2.cancelButton.hide()
            box2.yesButton.setText("확인")
            box2.exec()
            return
        refresh_table_callback()
        dialog.accept()

    dialog.button_edit.clicked.connect(do_edit)
    dialog.button_delete.clicked.connect(do_delete)
    dialog.button_close.clicked.connect(dialog.reject)
    dialog.exec()


def setup_admin_screen(window, stacked, ui_dir: str) -> None:
    """관리자 화면: 사이드바, 작업자 관리(목록·추가·정보 팝업), 출입 로그."""
    admin = window.page_admin
    admin.workerTable.setHorizontalHeaderLabels(["이름", "카드 UID", "등록일자"])
    admin.accessLogTable.setHorizontalHeaderLabels(
        ["작업자 이름", "출입 방향", "일시"]
    )
    admin.itemSortingLogTable.setHorizontalHeaderLabels(
        ["품목명", "QR 코드", "상태", "작업시간"]
    )

    # 재고 리포트: 도넛 차트 위젯
    from PyQt6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
    )
    inventory_chart = DonutChartWidget(admin.inventoryChartContainer)
    layout = QVBoxLayout(admin.inventoryChartContainer)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(inventory_chart)

    # 재고 현황: 아크+막대 차트 위젯
    inventory_status_chart = InventoryStatusChartWidget(admin.inventoryStatusChartContainer)
    status_layout = QVBoxLayout(admin.inventoryStatusChartContainer)
    status_layout.setContentsMargins(0, 0, 0, 0)
    status_layout.addWidget(inventory_status_chart)

    # 유통기한 통계 위젯
    expiration_stats = ExpirationStatsWidget(admin.expirationStatsContainer)
    exp_layout = QVBoxLayout(admin.expirationStatsContainer)
    exp_layout.setContentsMargins(0, 0, 0, 0)
    exp_layout.addWidget(expiration_stats)
    work_status_board = WorkStatusBoardWidget(admin.workStatusContainer)
    ws_layout = QVBoxLayout(admin.workStatusContainer)
    ws_layout.setContentsMargins(0, 0, 0, 0)
    ws_layout.addWidget(work_status_board)

    from PyQt6.QtCore import QDate
    admin.startDateEdit.setDate(QDate.currentDate().addDays(-7))
    admin.endDateEdit.setDate(QDate.currentDate())

    # 체크박스 연결
    admin.itemSearchCheckBox.toggled.connect(admin.itemSearchEdit.setEnabled)
    admin.dateSearchCheckBox.toggled.connect(admin.startDateEdit.setEnabled)
    admin.dateSearchCheckBox.toggled.connect(admin.endDateEdit.setEnabled)
    page_size = 20
    access_logs_cache: list[dict] = []
    item_logs_cache: list[dict] = []
    access_page = 1
    item_page = 1

    access_pager = QHBoxLayout()
    access_pager.setSpacing(6)
    access_prev_btn = QPushButton("이전")
    access_prev_btn.setMinimumHeight(34)
    access_page_label = QLabel("")
    access_page_input = QLineEdit()
    access_page_input.setPlaceholderText("페이지")
    access_page_input.setFixedWidth(72)
    access_go_btn = QPushButton("이동")
    access_go_btn.setMinimumHeight(34)
    access_next_btn = QPushButton("다음")
    access_next_btn.setMinimumHeight(34)
    access_pager.addStretch(1)
    access_pager.addWidget(access_prev_btn)
    access_pager.addWidget(access_page_label)
    access_pager.addWidget(access_page_input)
    access_pager.addWidget(access_go_btn)
    access_pager.addWidget(access_next_btn)
    access_pager.addStretch(1)
    # title(0) + search(1) + table(2) 바로 아래(3)
    admin.page_access_log.layout().insertLayout(3, access_pager)

    item_pager = QHBoxLayout()
    item_pager.setSpacing(6)
    item_prev_btn = QPushButton("이전")
    item_prev_btn.setMinimumHeight(34)
    item_page_label = QLabel("")
    item_page_input = QLineEdit()
    item_page_input.setPlaceholderText("페이지")
    item_page_input.setFixedWidth(72)
    item_go_btn = QPushButton("이동")
    item_go_btn.setMinimumHeight(34)
    item_next_btn = QPushButton("다음")
    item_next_btn.setMinimumHeight(34)
    item_pager.addStretch(1)
    item_pager.addWidget(item_prev_btn)
    item_pager.addWidget(item_page_label)
    item_pager.addWidget(item_page_input)
    item_pager.addWidget(item_go_btn)
    item_pager.addWidget(item_next_btn)
    item_pager.addStretch(1)
    # title(0) + filter(1) + table(2) 바로 아래(3)
    admin.page_item_sorting_log.layout().insertLayout(3, item_pager)

    def _format_created_at(created_at: str) -> str:
        """API created_at (ISO) → 날짜만 표시 (YYYY-MM-DD)."""
        if not created_at:
            return ""
        return created_at[:10] if len(created_at) >= 10 else created_at

    def _format_checked_at(checked_at: str) -> str:
        """API checked_at (ISO) → 로컬 표시용 (YYYY-MM-DD HH:MM:SS 또는 축약)."""
        if not checked_at:
            return ""
        if len(checked_at) >= 19:
            return checked_at[:19].replace("T", " ")
        return checked_at

    def _pagination_meta(total_count: int, current_page: int) -> tuple[int, int]:
        if total_count <= 0:
            return (0, 0)
        total_pages = (total_count + page_size - 1) // page_size
        page = max(1, min(current_page, total_pages))
        return (page, total_pages)

    def _parse_page(text: str, total_pages: int) -> int | None:
        try:
            n = int((text or "").strip())
        except ValueError:
            return None
        if total_pages <= 0:
            return None
        return max(1, min(n, total_pages))

    def _fit_table_height(table, visible_rows: int) -> None:
        """페이지 컨트롤이 표 바로 아래에 오도록 테이블 높이를 행 수에 맞춤."""
        rows = max(1, int(visible_rows))
        header_h = table.horizontalHeader().height()
        frame = table.frameWidth() * 2
        row_h = table.verticalHeader().defaultSectionSize()
        total_h = header_h + (row_h * rows) + frame + 4
        table.setMinimumHeight(total_h)
        table.setMaximumHeight(total_h)

    def _render_access_logs_page():
        nonlocal access_page
        admin.accessLogTable.setRowCount(0)
        page, total_pages = _pagination_meta(len(access_logs_cache), access_page)
        if page == 0:
            access_page_label.setText("0 / 0 (총 0건)")
            access_prev_btn.setEnabled(False)
            access_next_btn.setEnabled(False)
            _fit_table_height(admin.accessLogTable, 1)
            return
        access_page = page
        start = (access_page - 1) * page_size
        rows = access_logs_cache[start : start + page_size]
        for entry in rows:
            row = admin.accessLogTable.rowCount()
            admin.accessLogTable.insertRow(row)
            admin.accessLogTable.setVerticalHeaderItem(
                row, QTableWidgetItem(str(start + row + 1))
            )
            admin.accessLogTable.setItem(
                row, 0, QTableWidgetItem(entry.get("worker_name", ""))
            )
            direction = (entry.get("direction") or "").strip().lower()
            direction_label = "입장" if direction == "in" else ("퇴장" if direction == "out" else direction or "—")
            admin.accessLogTable.setItem(row, 1, QTableWidgetItem(direction_label))
            admin.accessLogTable.setItem(
                row,
                2,
                QTableWidgetItem(_format_checked_at(entry.get("checked_at", ""))),
            )
        access_page_label.setText(f"{access_page} / {total_pages} (총 {len(access_logs_cache)}건)")
        access_prev_btn.setEnabled(access_page > 1)
        access_next_btn.setEnabled(access_page < total_pages)
        _fit_table_height(admin.accessLogTable, len(rows))

    def _render_item_sorting_logs_page():
        nonlocal item_page
        admin.itemSortingLogTable.setRowCount(0)
        page, total_pages = _pagination_meta(len(item_logs_cache), item_page)
        if page == 0:
            item_page_label.setText("0 / 0 (총 0건)")
            item_prev_btn.setEnabled(False)
            item_next_btn.setEnabled(False)
            _fit_table_height(admin.itemSortingLogTable, 1)
            return
        item_page = page
        start = (item_page - 1) * page_size
        rows = item_logs_cache[start : start + page_size]
        for entry in rows:
            row = admin.itemSortingLogTable.rowCount()
            admin.itemSortingLogTable.insertRow(row)
            admin.itemSortingLogTable.setVerticalHeaderItem(
                row, QTableWidgetItem(str(start + row + 1))
            )
            admin.itemSortingLogTable.setItem(
                row, 0, QTableWidgetItem(entry.get("product_name", ""))
            )
            admin.itemSortingLogTable.setItem(
                row, 1, QTableWidgetItem(entry.get("box_qr_code", "") or "")
            )
            is_error = entry.get("is_error", False)
            status_text = "오류" if is_error else "정상"
            admin.itemSortingLogTable.setItem(row, 2, QTableWidgetItem(status_text))
            admin.itemSortingLogTable.setItem(
                row,
                3,
                QTableWidgetItem(_format_checked_at(entry.get("timestamp", ""))),
            )
        item_page_label.setText(f"{item_page} / {total_pages} (총 {len(item_logs_cache)}건)")
        item_prev_btn.setEnabled(item_page > 1)
        item_next_btn.setEnabled(item_page < total_pages)
        _fit_table_height(admin.itemSortingLogTable, len(rows))

    def refresh_access_logs(reset_page: bool = True):
        nonlocal access_logs_cache, access_page
        search_text = admin.accessLogSearchEdit.text().strip() if admin.accessLogSearchEdit else ""
        worker_name_filter = search_text if search_text else None
        try:
            logs = list_access_logs(worker_name=worker_name_filter)
        except (TimeoutError, RuntimeError, OSError, ConnectionError):
            access_logs_cache = []
            access_page = 1
            _render_access_logs_page()
            return
        access_logs_cache = logs or []
        if reset_page:
            access_page = 1
        _render_access_logs_page()

    def refresh_item_sorting_logs(reset_page: bool = True):
        nonlocal item_logs_cache, item_page
        # 체크박스 상태에 따라 검색 조건 포함 여부 결정
        start_date = None
        end_date = None
        search_text = None

        if admin.dateSearchCheckBox.isChecked():
            start_date = admin.startDateEdit.date().toString("yyyy-MM-dd")
            end_date = admin.endDateEdit.date().toString("yyyy-MM-dd")
        
        if admin.itemSearchCheckBox.isChecked():
            search_text = admin.itemSearchEdit.text().strip()

        try:
            logs = list_item_sorting_logs(
                start_date=start_date, end_date=end_date, search_text=search_text
            )
        except (TimeoutError, RuntimeError, OSError, ConnectionError):
            item_logs_cache = []
            item_page = 1
            _render_item_sorting_logs_page()
            return

        item_logs_cache = logs or []
        if reset_page:
            item_page = 1
        _render_item_sorting_logs_page()

    def refresh_workers():
        try:
            workers = list_workers()
        except (TimeoutError, RuntimeError, OSError, ConnectionError) as e:
            return  # 조용히 실패하거나 상태바에 표시 가능
        admin.workerTable.setRowCount(0)
        for w in workers:
            row = admin.workerTable.rowCount()
            admin.workerTable.insertRow(row)
            item0 = QTableWidgetItem(w.get("name", ""))
            item0.setData(Qt.ItemDataRole.UserRole, w.get("worker_id"))
            admin.workerTable.setItem(row, 0, item0)
            admin.workerTable.setItem(row, 1, QTableWidgetItem(w.get("card_uid", "")))
            admin.workerTable.setItem(row, 2, QTableWidgetItem(_format_created_at(w.get("created_at", ""))))

    def on_worker_cell_clicked(row: int, _column: int):
        if row < 0:
            return
        item0 = admin.workerTable.item(row, 0)
        worker_id = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        if worker_id is None:
            return
        name = item0.text() if item0 else ""
        uid = ""
        created_at_str = ""
        if admin.workerTable.item(row, 1):
            uid = admin.workerTable.item(row, 1).text()
        if admin.workerTable.item(row, 2):
            created_at_str = admin.workerTable.item(row, 2).text()
        _open_worker_info_dialog(
            window, ui_dir, worker_id, name, uid, created_at_str, refresh_workers
        )

    admin.workerTable.cellClicked.connect(on_worker_cell_clicked)

    def refresh_inventory_report():
        inv: list[dict] = []
        try:
            inv = list_inventory()
        except (TimeoutError, RuntimeError, OSError, ConnectionError):
            pass
        if not inv:
            # API 실패 시 soy_db 직접 조회 (fallback)
            from db.inventory import list_inventory as db_list_inventory
            inv = db_list_inventory()
        data = [(e.get("inventory_name", ""), e.get("current_qty", 0) or 0) for e in inv]
        inventory_chart.set_data(data)

    def refresh_inventory_status():
        stats: list[dict] = []
        try:
            stats = list_inventory_status_stats()
        except (TimeoutError, RuntimeError, OSError, ConnectionError):
            pass
        if not stats:
            from db.inventory import list_inventory_status_stats as db_list_stats
            stats = db_list_stats()
        inventory_status_chart.set_data(stats)
        inventory_status_chart.set_split_by_category(
            bool(admin.toggleInventoryStatusSplitButton.isChecked())
        )

    def refresh_expiration_stats():
        logs: list[dict] = []
        try:
            logs = list_item_sorting_logs()
        except (TimeoutError, RuntimeError, OSError, ConnectionError):
            pass
        expiration_stats.set_logs(logs)

    def refresh_work_status():
        orders: list[dict] = []
        processes: list[dict] = []
        logs: list[dict] = []
        try:
            orders = list_orders()
            processes = list_processes()
            logs = list_item_sorting_logs()
        except (TimeoutError, RuntimeError, OSError, ConnectionError):
            pass
        work_status_board.set_source_data(orders, processes, logs)

    def on_work_status_drop(order_id: int, from_status: str, to_status: str) -> bool:
        # 현재는 PENDING <-> DELIVERED 이동만 DB 반영
        if {from_status, to_status} != {"PENDING", "DELIVERED"}:
            refresh_work_status()
            return False
        try:
            if to_status == "DELIVERED":
                # 구버전 서버 호환: 기존 액션으로 delivered 처리
                order_mark_delivered(order_id=order_id)
            else:
                try:
                    order_set_status(order_id, to_status)
                except (TimeoutError, RuntimeError, OSError, ConnectionError) as e:
                    # 구버전 서버(Unknown action)일 때 PC 로컬 DB fallback
                    msg = str(e)
                    if "Unknown action: order_set_status" not in msg:
                        raise
                    from db.orders import set_order_status_pending

                    set_order_status_pending(order_id)
            return True
        except (TimeoutError, RuntimeError, OSError, ConnectionError) as e:
            box = MessageBox("상태 변경 실패", f"주문 #{order_id} 상태 변경 실패:\n{e!s}", window)
            box.cancelButton.hide()
            box.yesButton.setText("확인")
            box.exec()
            return False
        finally:
            refresh_work_status()

    work_status_board.set_status_change_handler(on_work_status_drop)

    def on_current_changed(index: int):
        if stacked.widget(index) == admin:
            current_idx = admin.admin_content_stack.currentIndex()
            if current_idx == 1:
                refresh_access_logs()
            elif current_idx == 2:
                refresh_item_sorting_logs()
            elif current_idx == 3:
                refresh_inventory_report()
            elif current_idx == 4:
                refresh_inventory_status()
            elif current_idx == 5:
                refresh_expiration_stats()
            elif current_idx == 6:
                refresh_work_status()
            else:
                refresh_workers()

    stacked.currentChanged.connect(on_current_changed)

    def on_admin_stack_changed(idx: int):
        if stacked.currentWidget() != admin:
            return
        if idx == 1:
            refresh_access_logs()
        elif idx == 2:
            refresh_item_sorting_logs()
        elif idx == 3:
            refresh_inventory_report()
        elif idx == 4:
            refresh_inventory_status()
        elif idx == 5:
            refresh_expiration_stats()
        elif idx == 6:
            refresh_work_status()
        else:
            refresh_workers()

    admin.admin_content_stack.currentChanged.connect(on_admin_stack_changed)

    def show_worker_management():
        admin.menu_worker_management.setChecked(True)
        admin.menu_access_log.setChecked(False)
        admin.menu_item_sorting_log.setChecked(False)
        admin.menu_inventory_status.setChecked(False)
        admin.menu_expiration_stats.setChecked(False)
        admin.menu_work_status.setChecked(False)
        admin.admin_content_stack.setCurrentIndex(0)
        refresh_workers()

    def show_access_log():
        admin.menu_worker_management.setChecked(False)
        admin.menu_access_log.setChecked(True)
        admin.menu_item_sorting_log.setChecked(False)
        admin.menu_inventory_status.setChecked(False)
        admin.menu_expiration_stats.setChecked(False)
        admin.menu_work_status.setChecked(False)
        admin.admin_content_stack.setCurrentIndex(1)
        refresh_access_logs()

    def show_item_sorting_log():
        admin.menu_worker_management.setChecked(False)
        admin.menu_access_log.setChecked(False)
        admin.menu_item_sorting_log.setChecked(True)
        admin.menu_inventory_status.setChecked(False)
        admin.menu_expiration_stats.setChecked(False)
        admin.menu_work_status.setChecked(False)
        admin.admin_content_stack.setCurrentIndex(2)
        refresh_item_sorting_logs()

    def show_inventory_status():
        admin.menu_worker_management.setChecked(False)
        admin.menu_access_log.setChecked(False)
        admin.menu_item_sorting_log.setChecked(False)
        admin.menu_inventory_status.setChecked(True)
        admin.menu_expiration_stats.setChecked(False)
        admin.menu_work_status.setChecked(False)
        admin.admin_content_stack.setCurrentIndex(4)
        refresh_inventory_status()

    def show_expiration_stats():
        admin.menu_worker_management.setChecked(False)
        admin.menu_access_log.setChecked(False)
        admin.menu_item_sorting_log.setChecked(False)
        admin.menu_inventory_status.setChecked(False)
        admin.menu_expiration_stats.setChecked(True)
        admin.menu_work_status.setChecked(False)
        admin.admin_content_stack.setCurrentIndex(5)
        refresh_expiration_stats()

    def show_work_status():
        admin.menu_worker_management.setChecked(False)
        admin.menu_access_log.setChecked(False)
        admin.menu_item_sorting_log.setChecked(False)
        admin.menu_inventory_status.setChecked(False)
        admin.menu_expiration_stats.setChecked(False)
        admin.menu_work_status.setChecked(True)
        admin.admin_content_stack.setCurrentIndex(6)
        refresh_work_status()

    admin.menu_worker_management.clicked.connect(show_worker_management)
    admin.menu_access_log.clicked.connect(show_access_log)
    admin.menu_item_sorting_log.clicked.connect(show_item_sorting_log)
    admin.menu_inventory_status.clicked.connect(show_inventory_status)
    admin.menu_expiration_stats.clicked.connect(show_expiration_stats)
    admin.menu_work_status.clicked.connect(show_work_status)
    admin.refreshInventoryButton.clicked.connect(refresh_inventory_report)
    admin.refreshInventoryStatusButton.clicked.connect(refresh_inventory_status)
    admin.refreshExpirationStatsButton.clicked.connect(refresh_expiration_stats)
    admin.refreshWorkStatusButton.clicked.connect(refresh_work_status)
    admin.toggleInventoryStatusSplitButton.toggled.connect(
        lambda checked: (
            inventory_status_chart.set_split_by_category(bool(checked)),
            admin.toggleInventoryStatusSplitButton.setText(
                "합산 보기" if checked else "진/국 분리 보기"
            ),
        )
    )

    def export_inventory_to_pdf():
        import tempfile
        from features.inventory_pdf import export_inventory_pdf
        data = inventory_chart.get_data()
        if not data:
            box = MessageBox("PDF 출력", "표시할 재고 데이터가 없습니다. 새로고침 후 다시 시도하세요.", window)
            box.cancelButton.hide()
            box.yesButton.setText("확인")
            box.exec()
            return
        pixmap = inventory_chart.grab()
        chart_path = None
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            chart_path = f.name
        try:
            pixmap.save(chart_path, "PNG")
            path, _ = QFileDialog.getSaveFileName(
                window,
                "PDF 저장",
                f"재고리포트_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                "PDF 파일 (*.pdf)",
            )
            if path:
                export_inventory_pdf(data, chart_path, path)
                box = MessageBox("저장 완료", f"PDF가 저장되었습니다.\n{path}", window)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
        except Exception as e:
            box = MessageBox("PDF 저장 실패", str(e), window)
            box.cancelButton.hide()
            box.yesButton.setText("확인")
            box.exec()
        finally:
            if chart_path and os.path.exists(chart_path):
                try:
                    os.unlink(chart_path)
                except Exception:
                    pass

    def export_inventory_status_to_pdf():
        from PyQt6.QtCore import QMarginsF, QPoint, QRect, Qt
        from PyQt6.QtGui import QColor, QFont, QPainter, QPageLayout, QPageSize, QPdfWriter, QPixmap

        path, _ = QFileDialog.getSaveFileName(
            window,
            "PDF 저장",
            f"재고현황_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            "PDF 파일 (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        try:
            current_split = bool(admin.toggleInventoryStatusSplitButton.isChecked())

            def capture_chart_pixmap(split_mode: bool):
                inventory_status_chart.set_split_by_category(split_mode)
                pm = QPixmap(inventory_status_chart.size())
                pm.fill(QColor("#ffffff"))
                p = QPainter(pm)
                inventory_status_chart.render(p, QPoint(0, 0))
                p.end()
                return pm

            agg_pixmap = capture_chart_pixmap(False)
            split_pixmap = capture_chart_pixmap(True)
            inventory_status_chart.set_split_by_category(current_split)

            if agg_pixmap.isNull() or split_pixmap.isNull():
                raise RuntimeError("차트를 캡처할 수 없습니다.")

            # --- mm 기반 레이아웃 (A4 210×297 mm 기준) ---
            DPI = 300
            MM_TO_PX = DPI / 25.4  # ≈ 11.81

            def mm2px(mm_val: float) -> int:
                return int(mm_val * MM_TO_PX)

            pdf = QPdfWriter(path)
            pdf.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            pdf.setResolution(DPI)
            # 좌측 여백 줄이고 우측 여백 늘려서 전체 콘텐츠를 왼쪽으로 이동
            pdf.setPageMargins(QMarginsF(10, 12, 20, 12), QPageLayout.Unit.Millimeter)

            painter = QPainter(pdf)
            content = pdf.pageLayout().paintRectPixels(DPI)
            painter.fillRect(content, QColor("#ffffff"))

            # 1) 헤더 영역: 전체 너비 사용, 출력시간 우측 정렬 (잘림 방지)
            header_h = mm2px(10)
            header_rect = QRect(content.x(), content.y(), content.width(), header_h)
            ts_font = QFont()
            ts_font.setPointSize(8)
            painter.setFont(ts_font)
            painter.setPen(QColor("#333333"))
            ts_text = f"출력시간 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            painter.drawText(
                header_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                ts_text,
            )

            # 2) 본문: 헤더 아래 동일 높이 2섹션
            gap = mm2px(6)
            body_top = content.y() + header_h
            body_h = content.height() - header_h
            section_h = (body_h - gap) // 2

            def draw_chart_section(sect_top: int, chart_pm: QPixmap) -> None:
                sect_rect = QRect(content.x(), sect_top, content.width(), section_h)
                sw, sh = chart_pm.width(), chart_pm.height()
                if sw <= 0 or sh <= 0:
                    return
                scale = min(sect_rect.width() / sw, sect_rect.height() / sh) * 0.95
                dw = max(1, int(sw * scale))
                dh = max(1, int(sh * scale))
                dx = sect_rect.x() + (sect_rect.width() - dw) // 2
                dy = sect_rect.y() + (sect_rect.height() - dh) // 2
                painter.drawPixmap(dx, dy, dw, dh, chart_pm)

            draw_chart_section(body_top, agg_pixmap)
            draw_chart_section(body_top + section_h + gap, split_pixmap)
            painter.end()

            box = MessageBox("저장 완료", f"PDF가 저장되었습니다.\n{path}", window)
            box.cancelButton.hide()
            box.yesButton.setText("확인")
            box.exec()
        except Exception as e:
            box = MessageBox("PDF 저장 실패", str(e), window)
            box.cancelButton.hide()
            box.yesButton.setText("확인")
            box.exec()

    admin.exportInventoryPdfButton.clicked.connect(export_inventory_to_pdf)
    admin.exportInventoryStatusPdfButton.clicked.connect(export_inventory_status_to_pdf)
    admin.refreshAccessLogButton.clicked.connect(refresh_access_logs)
    admin.itemSortingLogSearchButton.clicked.connect(refresh_item_sorting_logs)
    admin.itemSearchEdit.returnPressed.connect(refresh_item_sorting_logs)

    def on_access_prev():
        nonlocal access_page
        access_page = max(1, access_page - 1)
        _render_access_logs_page()

    def on_access_next():
        nonlocal access_page
        access_page += 1
        _render_access_logs_page()

    def on_item_prev():
        nonlocal item_page
        item_page = max(1, item_page - 1)
        _render_item_sorting_logs_page()

    def on_item_next():
        nonlocal item_page
        item_page += 1
        _render_item_sorting_logs_page()

    def on_access_go():
        nonlocal access_page
        _page, total_pages = _pagination_meta(len(access_logs_cache), access_page)
        target = _parse_page(access_page_input.text(), total_pages)
        if target is None:
            return
        access_page = target
        _render_access_logs_page()

    def on_item_go():
        nonlocal item_page
        _page, total_pages = _pagination_meta(len(item_logs_cache), item_page)
        target = _parse_page(item_page_input.text(), total_pages)
        if target is None:
            return
        item_page = target
        _render_item_sorting_logs_page()

    access_prev_btn.clicked.connect(on_access_prev)
    access_next_btn.clicked.connect(on_access_next)
    access_go_btn.clicked.connect(on_access_go)
    access_page_input.returnPressed.connect(on_access_go)
    item_prev_btn.clicked.connect(on_item_prev)
    item_next_btn.clicked.connect(on_item_next)
    item_go_btn.clicked.connect(on_item_go)
    item_page_input.returnPressed.connect(on_item_go)

    def on_access_log_search():
        refresh_access_logs(reset_page=True)

    def on_access_log_clear_filter():
        admin.accessLogSearchEdit.clear()
        refresh_access_logs(reset_page=True)

    admin.accessLogSearchButton.clicked.connect(on_access_log_search)
    admin.accessLogClearFilterButton.clicked.connect(on_access_log_clear_filter)
    admin.accessLogSearchEdit.returnPressed.connect(on_access_log_search)

    def back_to_lock():
        admin_logout()
        stacked.setCurrentIndex(0)

    admin.backButton.clicked.connect(back_to_lock)

    def on_add_worker_clicked():
        dialog = QDialog(window)
        uic.loadUi(os.path.join(ui_dir, "worker_registration_dialog.ui"), dialog)
        dialog._scanned_uid = None
        rfid_reader: SerialRFIDReader | None = None

        def on_rfid_ui(uid: str) -> None:
            """메인 스레드에서 UI 갱신 (TCP 콜백 또는 시리얼 시그널에서 호출)."""
            dialog._scanned_uid = uid or dialog._scanned_uid
            display_uid = (uid or dialog._scanned_uid) or "—"
            dialog.statusLabel.setText(
                f"카드 인식 완료 (UID: {display_uid}). 작업자 이름을 입력하세요."
            )
            dialog.workerNameEdit.setEnabled(True)
            dialog.button_ok.setEnabled(True)
            QTimer.singleShot(0, dialog.workerNameEdit.setFocus)

        if _USE_SERVER_RFID:
            # 서버 TCP 콜백은 reader 스레드에서 호출됨 → 시그널로 메인 스레드에 전달해야 UI 갱신됨
            bridge = _CardReadBridge()
            bridge.card_uid_received.connect(on_rfid_ui)

            def on_card_read_from_server(uid: str) -> None:
                bridge.card_uid_received.emit(uid)

            set_card_read_callback(on_card_read_from_server)
            try:
                get_first_admin_id()
                dialog.statusLabel.setText("서버에 연결됨. RFID 카드를 찍어주세요.")
            except (TimeoutError, RuntimeError, OSError, ConnectionError):
                dialog.statusLabel.setText(
                    "서버에 연결할 수 없습니다. soy-server가 실행 중인지 확인하세요."
                )
        else:
            port = get_register_serial_port()
            if port:
                rfid_reader = SerialRFIDReader(port, parent=dialog)
                rfid_reader.card_uid_received.connect(on_rfid_ui)

                def on_error(msg: str):
                    box = MessageBox("시리얼 오류", msg, dialog)
                    box.cancelButton.hide()
                    box.yesButton.setText("확인")
                    box.exec()

                rfid_reader.error_occurred.connect(on_error)
                rfid_reader.start()
                dialog.statusLabel.setText(f"RFID 카드를 찍어주세요. (시리얼: {port})")
            else:
                dialog.statusLabel.setText(
                    "시리얼 포트를 사용할 수 없습니다. Register Controller를 연결하세요."
                )

        def try_accept():
            QGuiApplication.inputMethod().commit()
            name = dialog.workerNameEdit.text().strip()
            if not name:
                box = MessageBox("입력 오류", "작업자 이름을 입력하세요.", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                dialog.workerNameEdit.setFocus()
                return
            uid = getattr(dialog, "_scanned_uid", None)
            if not uid or uid.strip() == "":
                box = MessageBox("입력 오류", "RFID 카드를 먼저 찍어주세요.", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                return
            admin_id = get_first_admin_id()
            if admin_id is None:
                box = MessageBox("등록 실패", "관리자가 등록되지 않았습니다.", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                return
            try:
                api_create_worker(admin_id, name, uid)
            except WorkerCreateConflict as e:
                box = MessageBox("등록 실패", e.detail, dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                return
            except (TimeoutError, RuntimeError, OSError, ConnectionError) as e:
                box = MessageBox(
                    "등록 실패",
                    f"서버 통신 오류. soy-server가 실행 중인지 확인하세요.\n{e!s}",
                    dialog,
                )
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                return
            box = MessageBox(
                "등록 완료",
                f"작업자 '{name}' (카드 UID: {uid}) 정보가 등록되었습니다.",
                dialog,
            )
            box.cancelButton.hide()
            box.yesButton.setText("확인")
            box.exec()
            refresh_workers()
            dialog.accept()

        def on_finished():
            if _USE_SERVER_RFID:
                set_card_read_callback(None)
            elif rfid_reader and rfid_reader.isRunning():
                rfid_reader.stop()
                rfid_reader.wait(2000)

        dialog.button_ok.clicked.connect(try_accept)
        dialog.button_cancel.clicked.connect(dialog.reject)
        dialog.workerNameEdit.returnPressed.connect(try_accept)
        dialog.finished.connect(on_finished)
        dialog.exec()

    admin.addWorkerButton.clicked.connect(on_add_worker_clicked)
