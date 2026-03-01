"""작업자 화면 — 돌아가기, 주문 관리(송장 QR 스캔), 분류하기(공정 시작/중지)."""
import json
import logging
from typing import Any, Callable

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QTableWidgetItem,
)

from api import (
    list_orders,
    list_processes,
    order_mark_delivered,
    process_start,
    process_stop,
    process_update,
)

logger = logging.getLogger(__name__)


class CameraQRThread(QThread):
    """카메라 프레임 수집 + QR 디코딩. 프레임은 미리보기용, 디코딩 결과는 입고 처리용."""
    frame_ready = pyqtSignal(QImage)
    qr_decoded = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._last_decoded: str | None = None
        self._cooldown_until: float = 0

    def run(self):
        import time
        import cv2
        from pyzbar import pyzbar

        self._running = True
        cap = None
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.warning("Camera open failed")
                return
            while self._running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    continue
                # 미리보기: BGR -> RGB, 좌우 반전(거울)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_rgb = cv2.flip(frame_rgb, 1)
                h, w, ch = frame_rgb.shape
                bytes_per_line = ch * w
                qimg = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                self.frame_ready.emit(qimg.copy())

                # QR 디코딩 (동일 QR 연속 인식 방지용 쿨다운)
                now = time.monotonic()
                if now < self._cooldown_until:
                    continue
                decoded_list = pyzbar.decode(frame)
                for obj in decoded_list:
                    if obj.type != "QRCODE":
                        continue
                    try:
                        data = obj.data.decode("utf-8", errors="strict").strip()
                    except Exception:
                        continue
                    if data and data != self._last_decoded:
                        self._last_decoded = data
                        self._cooldown_until = now + 2.0  # 2초 쿨다운
                        self.qr_decoded.emit(data)
                        break
        except Exception as e:
            logger.exception("CameraQRThread: %s", e)
        finally:
            if cap is not None:
                cap.release()
            self._running = False

    def stop(self):
        self._running = False


def _parse_qr_payload(data: str) -> dict[str, Any] | None:
    """QR 문자열이 JSON이면 파싱 (order_item_id, item_code 또는 order_id 등)."""
    data = (data or "").strip()
    if not data:
        return None
    if data.startswith("{"):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None
    # 숫자만 있으면 order_id로 간주
    try:
        return {"order_id": int(data)}
    except ValueError:
        return None


class InboundScanDialog(QDialog):
    """주문 입고 처리용 QR 스캔 팝업. 카메라 미리보기 + 스캔 시작/중지 + 닫기."""

    def __init__(self, parent=None, on_order_delivered: Callable[[], None] | None = None):
        super().__init__(parent)
        self.on_order_delivered = on_order_delivered or (lambda: None)
        self.setWindowTitle("주문 입고 처리 — 송장 QR 스캔")
        self.setMinimumSize(520, 480)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.cameraPreview = QLabel("카메라 미리보기")
        self.cameraPreview.setMinimumSize(480, 360)
        self.cameraPreview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cameraPreview.setFrameShape(QFrame.Shape.Box)
        layout.addWidget(self.cameraPreview)

        self.resultLabel = QLabel(
            "송장 QR을 카메라에 비춰 주세요. 스캔 시작 버튼을 누른 뒤 QR을 인식하면 자동으로 입고 처리됩니다."
        )
        self.resultLabel.setWordWrap(True)
        self.resultLabel.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.resultLabel)

        self.scanToggleButton = QPushButton("QR 스캔 시작")
        self.scanToggleButton.setMinimumHeight(40)
        layout.addWidget(self.scanToggleButton)

        self.closeButton = QPushButton("닫기")
        self.closeButton.setMinimumHeight(36)
        layout.addWidget(self.closeButton)

        self._camera_thread: CameraQRThread | None = None
        self._scan_active = False

        self.scanToggleButton.clicked.connect(self._on_scan_toggle)
        self.closeButton.clicked.connect(self.reject)

    def _stop_camera(self):
        if self._camera_thread and self._camera_thread.isRunning():
            self._camera_thread.stop()
            self._camera_thread.wait(3000)
        self.cameraPreview.clear()
        self.cameraPreview.setText("카메라 미리보기")
        self.scanToggleButton.setText("QR 스캔 시작")
        self._scan_active = False

    def _on_scan_toggle(self):
        if self._scan_active:
            self._stop_camera()
            self.resultLabel.setText(
                "송장 QR을 카메라에 비춰 주세요. 스캔 시작 버튼을 누른 뒤 QR을 인식하면 자동으로 입고 처리됩니다."
            )
            return
        try:
            self._camera_thread = CameraQRThread(self)
        except Exception as e:
            self.resultLabel.setText(f"카메라를 사용할 수 없습니다: {e}")
            return

        def on_frame(qimg: QImage):
            pix = QPixmap.fromImage(qimg)
            self.cameraPreview.setPixmap(
                pix.scaled(
                    self.cameraPreview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        def on_qr(data: str):
            payload = _parse_qr_payload(data)
            if not payload:
                self.resultLabel.setText("인식된 QR 형식을 처리할 수 없습니다.")
                return
            order_id = payload.get("order_id")
            order_item_id = payload.get("order_item_id")
            if order_id is None and order_item_id is None:
                self.resultLabel.setText(
                    "QR에 주문 정보가 없습니다. (order_id 또는 order_item_id 필요)"
                )
                return
            try:
                if order_id is not None:
                    order_mark_delivered(order_id=int(order_id))
                else:
                    order_mark_delivered(order_item_id=int(order_item_id))
                self.resultLabel.setText("입고 처리되었습니다.")
                self.on_order_delivered()
            except RuntimeError as e:
                err = str(e)
                if "이미 입고한" in err:
                    self.resultLabel.setText("이미 입고한 주문입니다.")
                else:
                    self.resultLabel.setText(f"처리 실패: {err}")
            except (TimeoutError, OSError, ConnectionError) as e:
                self.resultLabel.setText(
                    f"서버 연결 실패. 서버가 실행 중인지 확인하세요.\n{e!s}"
                )

        self._camera_thread.frame_ready.connect(on_frame)
        self._camera_thread.qr_decoded.connect(on_qr)
        self._camera_thread.start()
        self.scanToggleButton.setText("QR 스캔 중지")
        self.resultLabel.setText("QR을 카메라에 비춰 주세요…")
        self._scan_active = True

    def reject(self):
        self._stop_camera()
        super().reject()

    def closeEvent(self, event):
        self._stop_camera()
        super().closeEvent(event)


def setup_worker_screen(window, stacked) -> None:
    """작업자 화면: 사이드바(주문 관리 메뉴), 주문 관리 페이지(송장 QR → 주문 delivered)."""
    worker = window.page_worker

    def back_to_lock():
        stacked.setCurrentIndex(0)

    worker.backButton.clicked.connect(back_to_lock)

    # 기본 페이지: 환영 화면(page_welcome). 주문 관리 클릭 시 page_inbound로 전환.
    stack = worker.worker_content_stack
    stack.setCurrentIndex(0)  # page_welcome

    # .ui 로더가 contentsMargins 4값을 처리하지 못하므로 Python에서 설정
    welcome_page = stack.widget(0)
    if welcome_page.layout():
        welcome_page.layout().setContentsMargins(32, 32, 32, 32)
    card = worker.findChild(QFrame, "welcome_card")
    if card and card.layout():
        card.layout().setContentsMargins(40, 40, 40, 40)

    def on_menu_inbound_clicked():
        if worker.menu_inbound.isChecked():
            worker.menu_classify.setChecked(False)
            stack.setCurrentIndex(1)  # page_inbound
        else:
            stack.setCurrentIndex(0)  # page_welcome

    def on_menu_classify_clicked():
        if worker.menu_classify.isChecked():
            worker.menu_inbound.setChecked(False)
            stack.setCurrentIndex(3)  # page_classify (0=welcome, 1=inbound, 2=order_detail, 3=classify)
            _refresh_classify_list()
        else:
            stack.setCurrentIndex(0)  # page_welcome

    worker.menu_inbound.clicked.connect(on_menu_inbound_clicked)
    worker.menu_classify.clicked.connect(on_menu_classify_clicked)

    _inbound_orders_list: list[dict] = []

    def _qty_by_code(items: list[dict], code: str) -> int:
        return sum(
            it.get("expected_qty", 0) or 0
            for it in items
            if (it.get("item_code") or "").strip().upper() == code.upper()
        )

    def _refresh_inbound_order_list():
        """주문 목록 테이블 갱신 (주문 ID, 주문일, 입고 여부, 1L, 2L)."""
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
            qty_1l = _qty_by_code(items, "1L")
            qty_2l = _qty_by_code(items, "2L")
            worker.orderTable.setItem(row, 0, QTableWidgetItem(str(oid)))
            worker.orderTable.item(row, 0).setData(Qt.ItemDataRole.UserRole, oid)
            worker.orderTable.setItem(row, 1, QTableWidgetItem(date_str))
            worker.orderTable.setItem(row, 2, QTableWidgetItem(입고_str))
            worker.orderTable.setItem(row, 3, QTableWidgetItem(str(qty_1l)))
            worker.orderTable.setItem(row, 4, QTableWidgetItem(str(qty_2l)))
            for c in range(5):
                worker.orderTable.item(row, c).setFlags(flags_ro)
        worker.orderTable.setColumnWidth(0, 72)   # 주문 ID
        worker.orderTable.setColumnWidth(1, 150)   # 주문일 (넓게)
        worker.orderTable.setColumnWidth(2, 100)   # 입고 여부 (넓게)
        worker.orderTable.setColumnWidth(3, 44)    # 1L (좁게)
        worker.orderTable.setColumnWidth(4, 44)    # 2L (좁게)

    # 주문 관리 클릭 시 목록 갱신
    def _on_menu_inbound_clicked_extra():
        on_menu_inbound_clicked()
        _refresh_inbound_order_list()

    worker.menu_inbound.clicked.disconnect(on_menu_inbound_clicked)
    worker.menu_inbound.clicked.connect(_on_menu_inbound_clicked_extra)

    # ----- 주문 관리 페이지: 주문 입고 처리 버튼 → QR 스캔 팝업 -----
    def on_inbound_scan_button():
        dialog = InboundScanDialog(
            parent=window,
            on_order_delivered=_refresh_inbound_order_list,
        )
        dialog.exec()
        _refresh_inbound_order_list()

    worker.inboundScanButton.clicked.connect(on_inbound_scan_button)

    # 주문 목록 행 클릭 → 상세 페이지로 이동 (품목 리스트 표시)
    PAGE_ORDER_DETAIL = 2  # stack index

    def on_order_row_clicked(row: int, _column: int):
        if row < 0:
            return
        item0 = worker.orderTable.item(row, 0)
        oid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        if oid is None:
            return
        order = next((o for o in _inbound_orders_list if o.get("order_id") == oid), None)
        if not order:
            return
        worker.label_order_detail_title.setText(f"주문 상세 # {oid}")
        worker.orderDetailTable.setHorizontalHeaderLabels(["품목명", "품목 코드", "수량"])
        worker.orderDetailTable.setRowCount(0)
        flags_ro = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        for it in order.get("items") or []:
            # 품목명 = 서버에서 오는 product_name (브랜드 + 간장종류 + 용량)
            product_name = it.get("product_name") or it.get("item_code") or "—"
            code = it.get("item_code") or ""
            r = worker.orderDetailTable.rowCount()
            worker.orderDetailTable.insertRow(r)
            worker.orderDetailTable.setItem(r, 0, QTableWidgetItem(product_name))
            worker.orderDetailTable.setItem(r, 1, QTableWidgetItem(code))
            worker.orderDetailTable.setItem(r, 2, QTableWidgetItem(str(it.get("expected_qty", 0))))
            for c in range(3):
                worker.orderDetailTable.item(r, c).setFlags(flags_ro)
        worker.orderDetailTable.setColumnWidth(0, 180)
        worker.orderDetailTable.setColumnWidth(1, 90)
        stack.setCurrentIndex(PAGE_ORDER_DETAIL)

    worker.orderTable.cellDoubleClicked.connect(on_order_row_clicked)

    def on_order_detail_back():
        stack.setCurrentIndex(1)  # page_inbound

    worker.orderDetailBackButton.clicked.connect(on_order_detail_back)

    # ----- 분류하기 페이지: 공정 목록, 한 번에 하나만 시작/중지 -----
    _classify_processes: list[dict[str, Any]] = []

    def _refresh_classify_list():
        nonlocal _classify_processes
        try:
            _classify_processes = list_processes()
        except (TimeoutError, OSError, ConnectionError) as e:
            worker.classifyResultLabel.setText(f"서버 연결 실패.\n{e!s}")
            worker.processTable.setRowCount(0)
            worker.label_running_status.setText("현재 진행 중: (목록 불러오기 실패)")
            worker.classifyToggleButton.setEnabled(False)
            return
        except RuntimeError as e:
            worker.classifyResultLabel.setText(str(e))
            worker.processTable.setRowCount(0)
            worker.label_running_status.setText("현재 진행 중: (오류)")
            worker.classifyToggleButton.setEnabled(False)
            return
        worker.classifyResultLabel.setText("")
        running = next((p for p in _classify_processes if (p.get("status") or "").upper() == "RUNNING"), None)
        worker.processTable.setHorizontalHeaderLabels(
            ["공정 ID", "주문 ID", "상태", "시작 시각", "종료 시각", "1L", "2L", "미분류"]
        )
        worker.processTable.setRowCount(0)
        worker.processTable.blockSignals(True)
        try:
            for p in _classify_processes:
                row = worker.processTable.rowCount()
                worker.processTable.insertRow(row)
                pid = p.get("process_id")
                oid = p.get("order_id")
                st = (p.get("status") or "").upper()
                def _fmt_dt(s: str | None) -> str:
                    if not s:
                        return "—"
                    return s.replace("T", " ")[:16]  # YYYY-MM-DD HH:MM
                start_str = _fmt_dt(p.get("start_time"))
                end_str = _fmt_dt(p.get("end_time"))
                s1l = p.get("success_1l_qty", 0)
                s2l = p.get("success_2l_qty", 0)
                uncl = p.get("unclassified_qty", 0)
                flags_ro = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                flags_ed = flags_ro | Qt.ItemFlag.ItemIsEditable
                item0 = QTableWidgetItem(str(pid))
                item0.setData(Qt.ItemDataRole.UserRole, pid)
                item0.setFlags(flags_ro)
                worker.processTable.setItem(row, 0, item0)
                for col, val in [(1, str(oid)), (2, st), (3, start_str), (4, end_str)]:
                    it = QTableWidgetItem(val)
                    it.setFlags(flags_ro)
                    worker.processTable.setItem(row, col, it)
                it5 = QTableWidgetItem(str(s1l))
                it5.setFlags(flags_ed)
                worker.processTable.setItem(row, 5, it5)
                it6 = QTableWidgetItem(str(s2l))
                it6.setFlags(flags_ed)
                worker.processTable.setItem(row, 6, it6)
                it7 = QTableWidgetItem(str(uncl))
                it7.setFlags(flags_ed)
                worker.processTable.setItem(row, 7, it7)
        finally:
            worker.processTable.blockSignals(False)
        # 시각 컬럼·수량 컬럼 너비 고정
        worker.processTable.setColumnWidth(3, 150)
        worker.processTable.setColumnWidth(4, 150)
        worker.processTable.setColumnWidth(5, 50)
        worker.processTable.setColumnWidth(6, 50)
        worker.processTable.setColumnWidth(7, 55)
        if running:
            worker.label_running_status.setText(f"현재 진행 중: 공정 #{running['process_id']} (주문 #{running['order_id']})")
        else:
            worker.label_running_status.setText("현재 진행 중: 없음")
        _classify_update_toggle_button()

    def _classify_update_toggle_button():
        """선택된 공정에 따라 [시작]/[중지] 버튼 문구·활성화."""
        running = next((p for p in _classify_processes if (p.get("status") or "").upper() == "RUNNING"), None)
        row = worker.processTable.currentRow()
        item0 = worker.processTable.item(row, 0) if row >= 0 else None
        pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        p = next((x for x in _classify_processes if x.get("process_id") == pid), None) if pid is not None else None
        is_selected_running = p and (p.get("status") or "").upper() == "RUNNING"
        if is_selected_running:
            worker.classifyToggleButton.setText("중지")
            worker.classifyToggleButton.setEnabled(True)
        elif pid and not running:
            worker.classifyToggleButton.setText("시작")
            worker.classifyToggleButton.setEnabled(True)
        else:
            worker.classifyToggleButton.setText("시작")
            worker.classifyToggleButton.setEnabled(False)

    def on_classify_selection_changed():
        _classify_update_toggle_button()

    def on_classify_toggle():
        row = worker.processTable.currentRow()
        if row < 0:
            worker.classifyResultLabel.setText("공정을 선택하세요.")
            return
        item0 = worker.processTable.item(row, 0)
        pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        if pid is None:
            return
        p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
        is_running = p and (p.get("status") or "").upper() == "RUNNING"
        try:
            if is_running:
                process_stop(int(pid))
                worker.classifyResultLabel.setText("공정을 중지했습니다.")
            else:
                process_start(int(pid))
                worker.classifyResultLabel.setText("공정을 시작했습니다.")
            _refresh_classify_list()
        except RuntimeError as e:
            worker.classifyResultLabel.setText(f"처리 실패: {e}")
        except (TimeoutError, OSError, ConnectionError) as e:
            worker.classifyResultLabel.setText(f"서버 연결 실패.\n{e!s}")

    def on_classify_cell_changed(row: int, col: int):
        if col not in (5, 6, 7):
            return
        item0 = worker.processTable.item(row, 0)
        pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        if pid is None:
            return
        item = worker.processTable.item(row, col)
        if not item:
            return
        raw = item.text().strip()
        try:
            val = int(raw)
            if val < 0:
                raise ValueError("0 이상이어야 합니다")
        except ValueError:
            worker.processTable.blockSignals(True)
            p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
            old = (
                p.get("success_1l_qty", 0) if col == 5
                else p.get("success_2l_qty", 0) if col == 6
                else p.get("unclassified_qty", 0)
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText("1L, 2L, 미분류에는 0 이상의 숫자만 입력하세요.")
            return
        field = {5: "success_1l_qty", 6: "success_2l_qty", 7: "unclassified_qty"}[col]
        try:
            process_update(int(pid), **{field: val})
            for x in _classify_processes:
                if x.get("process_id") == pid:
                    x[field] = val
                    break
            worker.classifyResultLabel.setText("수량이 저장되었습니다.")
        except RuntimeError as e:
            worker.processTable.blockSignals(True)
            p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
            old = (
                p.get("success_1l_qty", 0) if col == 5
                else p.get("success_2l_qty", 0) if col == 6
                else p.get("unclassified_qty", 0)
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText(f"저장 실패: {e}")
        except (TimeoutError, OSError, ConnectionError) as e:
            worker.processTable.blockSignals(True)
            p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
            old = (
                p.get("success_1l_qty", 0) if col == 5
                else p.get("success_2l_qty", 0) if col == 6
                else p.get("unclassified_qty", 0)
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText(f"서버 연결 실패.\n{e!s}")

    worker.processTable.itemChanged.connect(
        lambda item: on_classify_cell_changed(item.row(), item.column())
    )
    worker.processTable.itemSelectionChanged.connect(on_classify_selection_changed)
    worker.classifyToggleButton.clicked.connect(on_classify_toggle)
    worker.classifyRefreshButton.clicked.connect(_refresh_classify_list)

    def stop_camera_if_leaving():
        # QR 스캔은 팝업 다이얼로그에서만 동작하므로 화면 전환 시 별도 정리 불필요
        pass

    def stop_camera_if_switching_to_welcome(index: int):
        # QR 스캔은 팝업에서만 동작하므로 페이지 전환 시 별도 정리 불필요
        pass

    stacked.currentChanged.connect(lambda _: stop_camera_if_leaving())
    stack.currentChanged.connect(stop_camera_if_switching_to_welcome)
