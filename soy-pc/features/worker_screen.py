"""작업자 화면 — 돌아가기, 주문 관리(송장 QR 스캔), 분류하기(공정 시작/중지 + ESP32-CAM + FSM)."""

import json
import logging
import struct
from typing import Any, Callable

from mqtt_client import mqtt_client

MQTT_TOPIC_CONTROL = "device/control"
MQTT_TOPIC_SENSOR = "device/sensor"
MQTT_TOPIC_STATUS = "device/status"

from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
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


# ── ESP32-CAM UDP 스트림 수신 스레드 ─────────────────────────────
class UdpCameraThread(QThread):
    """ESP32-CAM UDP 청크 스트림 수신 → JPEG 재조립 → QImage + QR 디코딩."""

    frame_ready = pyqtSignal(QImage)
    qr_decoded = pyqtSignal(str)

    UDP_PORT = 8021
    MAGIC = b"IMG"  # 3 bytes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._last_decoded: str | None = None
        self._cooldown_until: float = 0

    def run(self):
        import socket
        import time
        import cv2
        import numpy as np

        # pyzbar는 libzbar0 시스템 패키지 필요 — 없으면 QR 디코딩만 비활성화
        pyzbar_mod = None
        try:
            from pyzbar import pyzbar as _pyzbar

            pyzbar_mod = _pyzbar
            logger.info("[UdpCam] pyzbar 로드 OK")
        except ImportError:
            logger.warning("pyzbar 로드 실패 (libzbar0 미설치?). QR 디코딩 비활성화.")

        self._running = True
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.UDP_PORT))
            sock.settimeout(1.0)
            logger.info("[UdpCam] UDP 소켓 바인드 OK (port %d)", self.UDP_PORT)

            # 청크 재조립 버퍼: {image_id: {total, chunks: {idx: data}}}
            buffers: dict[int, dict] = {}
            frame_count = 0

            while self._running:
                try:
                    data, _ = sock.recvfrom(65535)
                except socket.timeout:
                    continue

                if len(data) < 10 or data[:3] != self.MAGIC:
                    continue

                # 프로토콜: IMG(3) + frame_type(1) + image_id(2 LE) + total_chunks(2 LE) + chunk_index(2 LE) + JPEG data
                _frame_type = data[3]
                image_id = struct.unpack_from("<H", data, 4)[0]
                total_chunks = struct.unpack_from("<H", data, 6)[0]
                chunk_index = struct.unpack_from("<H", data, 8)[0]
                jpeg_part = data[10:]

                if image_id not in buffers:
                    # 이전 이미지 버퍼 정리 (최대 2개 유지)
                    if len(buffers) > 2:
                        oldest = min(buffers.keys())
                        del buffers[oldest]
                    buffers[image_id] = {"total": total_chunks, "chunks": {}}

                buf = buffers[image_id]
                buf["chunks"][chunk_index] = jpeg_part

                if len(buf["chunks"]) < buf["total"]:
                    continue

                # 모든 청크 수신 완료 → JPEG 재조립
                jpeg_data = b""
                for i in range(buf["total"]):
                    jpeg_data += buf["chunks"].get(i, b"")
                del buffers[image_id]

                # JPEG 디코드
                arr = np.frombuffer(jpeg_data, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                # 상하반전 (QR 인식을 위해 필요)
                frame = cv2.flip(frame, 0)

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                qimg = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.frame_ready.emit(qimg.copy())

                frame_count += 1

                # QR 디코딩 (pyzbar 사용 가능한 경우만, 2초 쿨다운)
                if pyzbar_mod is None:
                    continue
                now = time.monotonic()
                if now < self._cooldown_until:
                    continue
                decoded_list = pyzbar_mod.decode(frame)
                if decoded_list and frame_count % 30 == 0:
                    logger.info(
                        "[UdpCam] QR 감지 %d개: %s",
                        len(decoded_list),
                        [o.data[:40] for o in decoded_list],
                    )
                for obj in decoded_list:
                    if obj.type != "QRCODE":
                        continue
                    try:
                        qr_data = obj.data.decode("utf-8", errors="strict").strip()
                    except Exception:
                        continue
                    if qr_data:
                        # 쿨다운만 적용, 동일 QR 재인식 허용
                        self._last_decoded = qr_data
                        self._cooldown_until = now + 2.0
                        logger.info("[UdpCam] QR 발행: %s", qr_data)
                        self.qr_decoded.emit(qr_data)
                        break

        except Exception as e:
            logger.exception("UdpCameraThread: %s", e)
        finally:
            if sock:
                sock.close()
            self._running = False

    def stop(self):
        self._running = False


# ── MQTT → Qt 시그널 브릿지 (스레드 안전) ────────────────────────
class MqttSignalBridge(QObject):
    """paho MQTT 스레드에서 Qt 메인 스레드로 안전하게 신호 전달."""

    sensor_received = pyqtSignal(str)  # device/sensor 페이로드
    status_received = pyqtSignal(str)  # device/status 페이로드

    def __init__(self, parent=None):
        super().__init__(parent)
        mqtt_client.subscribe(MQTT_TOPIC_SENSOR, self._on_sensor)
        mqtt_client.subscribe(MQTT_TOPIC_STATUS, self._on_status)

    def _on_sensor(self, _topic: str, payload: str) -> None:
        self.sensor_received.emit(payload)

    def _on_status(self, _topic: str, payload: str) -> None:
        self.status_received.emit(payload)


# ── 기존 로컬 카메라 QR 스레드 (입고 스캔용) ─────────────────────
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

        pyzbar_mod = None
        try:
            from pyzbar import pyzbar as _pyzbar

            pyzbar_mod = _pyzbar
        except ImportError:
            logger.warning("pyzbar 로드 실패 (libzbar0 미설치?). QR 디코딩 비활성화.")

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
                qimg = QImage(
                    frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
                )
                self.frame_ready.emit(qimg.copy())

                # QR 디코딩 (동일 QR 연속 인식 방지용 쿨다운)
                if pyzbar_mod is None:
                    continue
                now = time.monotonic()
                if now < self._cooldown_until:
                    continue
                decoded_list = pyzbar_mod.decode(frame)
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

    def __init__(
        self, parent=None, on_order_delivered: Callable[[], None] | None = None
    ):
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


# ── FSM 상태 색상 ─────────────────────────────────────────────
_FSM_COLORS = {
    "IDLE": "#e74c3c",
    "RUNNING": "#27ae60",
    "SORTING": "#3498db",
    "WARNING": "#f39c12",
}
_FSM_INACTIVE = "#e0e0e0"
_FSM_STATES = ["IDLE", "RUNNING", "SORTING", "WARNING"]
_FSM_LABELS = {"IDLE": "대기", "RUNNING": "가동", "SORTING": "분류", "WARNING": "경고"}


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
    warehouse_page = stack.widget(4)  # page_warehouse
    if warehouse_page.layout():
        warehouse_page.layout().setContentsMargins(32, 32, 32, 32)
    card = worker.findChild(QFrame, "welcome_card")
    if card and card.layout():
        card.layout().setContentsMargins(40, 40, 40, 40)

    def on_menu_inbound_clicked():
        if worker.menu_inbound.isChecked():
            worker.menu_classify.setChecked(False)
            worker.menu_warehouse.setChecked(False)
            stack.setCurrentIndex(1)  # page_inbound
        else:
            stack.setCurrentIndex(0)  # page_welcome

    def on_menu_classify_clicked():
        if worker.menu_classify.isChecked():
            worker.menu_inbound.setChecked(False)
            worker.menu_warehouse.setChecked(False)
            stack.setCurrentIndex(
                3
            )  # page_classify (0=welcome, 1=inbound, 2=order_detail, 3=classify, 4=warehouse)
            _refresh_classify_list()
        else:
            stack.setCurrentIndex(0)  # page_welcome

    PAGE_WAREHOUSE = 4

    def on_menu_warehouse_clicked():
        if worker.menu_warehouse.isChecked():
            worker.menu_inbound.setChecked(False)
            worker.menu_classify.setChecked(False)
            stack.setCurrentIndex(PAGE_WAREHOUSE)
            _refresh_warehouse_chart()
        else:
            stack.setCurrentIndex(0)  # page_welcome

    worker.menu_inbound.clicked.connect(on_menu_inbound_clicked)
    worker.menu_classify.clicked.connect(on_menu_classify_clicked)
    worker.menu_warehouse.clicked.connect(on_menu_warehouse_clicked)

    _inbound_orders_list: list[dict] = []

    def _qty_by_capacity(items: list[dict], capacity: str) -> int:
        """용량(1L, 2L 등)으로 주문 품목 수량 합계. capacity는 서버 products 기준, 없으면 item_code 접미사(_1l, _2l)로 판별."""
        cap_upper = (capacity or "").strip().upper()
        total = 0
        for it in items:
            qty = it.get("expected_qty", 0) or 0
            item_cap = (it.get("capacity") or "").strip().upper()
            if item_cap and item_cap == cap_upper:
                total += qty
                continue
            # 서버가 capacity를 안 주는 경우: item_code 접미사로 판별 (예: sampyo_jin_1l → 1L)
            code = (it.get("item_code") or "").strip().upper()
            if code.endswith("_1L") and cap_upper == "1L":
                total += qty
            elif code.endswith("_2L") and cap_upper == "2L":
                total += qty
        return total

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
        worker.orderTable.setColumnWidth(0, 72)  # 주문 ID
        worker.orderTable.setColumnWidth(1, 150)  # 주문일 (넓게)
        worker.orderTable.setColumnWidth(2, 100)  # 입고 여부 (넓게)
        worker.orderTable.setColumnWidth(3, 44)  # 1L (좁게)
        worker.orderTable.setColumnWidth(4, 44)  # 2L (좁게)

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
            # 품목명 = 서버에서 오는 product_name (브랜드 + 간장종류 + 용량)
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
        stack.setCurrentIndex(1)  # page_inbound

    worker.orderDetailBackButton.clicked.connect(on_order_detail_back)

    # ═══════════════════════════════════════════════════════════════
    # ═══ 분류하기 페이지: 모니터 프레임 + 공정 목록 + 워크플로우 ═══
    # ═══════════════════════════════════════════════════════════════

    _classify_processes: list[dict[str, Any]] = []
    _current_process_id: list[int | None] = [None]  # mutable ref
    _current_order_items: list[list[dict]] = [[]]  # 현재 주문 품목 캐시

    # ── 분류 페이지 모니터 프레임 생성 (프로그래밍 방식) ─────────────
    classify_layout = worker.verticalLayout_classify

    monitor_frame = QFrame()
    monitor_frame.setFrameShape(QFrame.Shape.StyledPanel)
    monitor_frame.setStyleSheet(
        "QFrame { background: #fafafa; border: 1px solid #ddd; border-radius: 6px; }"
    )
    monitor_layout = QHBoxLayout(monitor_frame)
    monitor_layout.setContentsMargins(12, 12, 12, 12)
    monitor_layout.setSpacing(16)

    # 좌측: 카메라 프리뷰
    cam_preview = QLabel("카메라 대기")
    cam_preview.setFixedSize(320, 240)
    cam_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cam_preview.setStyleSheet(
        "background: #222; color: #888; border: 1px solid #555; font-size: 13px;"
    )
    monitor_layout.addWidget(cam_preview)

    # 우측: FSM + QR + 근접센서 상태
    info_layout = QVBoxLayout()
    info_layout.setSpacing(8)

    # FSM 상태 표시 라인
    fsm_title = QLabel("공정 단계")
    fsm_title.setStyleSheet("font-weight: bold; font-size: 13px; border: none;")
    info_layout.addWidget(fsm_title)

    fsm_row = QHBoxLayout()
    fsm_row.setSpacing(4)
    fsm_state_labels: dict[str, QLabel] = {}
    for i, st in enumerate(_FSM_STATES):
        lbl = QLabel(_FSM_LABELS[st])
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedHeight(28)
        lbl.setMinimumWidth(52)
        lbl.setStyleSheet(
            f"background: {_FSM_INACTIVE}; color: #666; border-radius: 4px; "
            f"font-size: 12px; padding: 2px 8px; border: none;"
        )
        fsm_state_labels[st] = lbl
        fsm_row.addWidget(lbl)
        if i < len(_FSM_STATES) - 1:
            arrow = QLabel("->")
            arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
            arrow.setFixedWidth(20)
            arrow.setStyleSheet("color: #999; font-size: 11px; border: none;")
            fsm_row.addWidget(arrow)
    fsm_row.addStretch()
    info_layout.addLayout(fsm_row)

    # QR 인식 상태
    qr_status_label = QLabel("QR 인식: 대기 중")
    qr_status_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")
    qr_status_label.setWordWrap(True)
    info_layout.addWidget(qr_status_label)

    # 근접센서 상태
    proximity_label = QLabel("근접센서: 감지 되지 않음")
    proximity_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")
    info_layout.addWidget(proximity_label)

    # 경고 상태
    warning_label = QLabel("경고: (없음)")
    warning_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")
    warning_label.setWordWrap(True)
    info_layout.addWidget(warning_label)

    info_layout.addStretch()
    monitor_layout.addLayout(info_layout)
    monitor_layout.setStretch(0, 0)  # 카메라 고정
    monitor_layout.setStretch(1, 1)  # 정보 영역 확장

    # 기존 classify 레이아웃의 타이틀(index 0) 아래에 삽입
    classify_layout.insertWidget(1, monitor_frame)

    # ── FSM 상태 UI 업데이트 헬퍼 ────────────────────────────────
    def _update_fsm_display(active_state: str):
        for st, lbl in fsm_state_labels.items():
            if st == active_state:
                color = _FSM_COLORS.get(st, _FSM_INACTIVE)
                lbl.setStyleSheet(
                    f"background: {color}; color: white; border-radius: 4px; "
                    f"font-size: 12px; font-weight: bold; padding: 2px 8px; border: none;"
                )
            else:
                lbl.setStyleSheet(
                    f"background: {_FSM_INACTIVE}; color: #666; border-radius: 4px; "
                    f"font-size: 12px; padding: 2px 8px; border: none;"
                )

    # 초기 FSM 표시
    _update_fsm_display("IDLE")

    # ── MqttSignalBridge ─────────────────────────────────────────
    mqtt_bridge = MqttSignalBridge(parent=window)

    def _on_status_received(payload: str):
        """device/status 수신 → FSM 표시 업데이트 + 워치독."""
        try:
            data = json.loads(payload)
            state = data.get("state", "")
        except (json.JSONDecodeError, AttributeError):
            state = payload.strip()
        if state in _FSM_STATES:
            _update_fsm_display(state)

        # 워치독: ESP32가 IDLE인데 PC에서 공정이 돌아가고 있으면 SORT_START 재전송
        if state == "IDLE" and _current_process_id[0] is not None:
            logger.warning(
                "[Watchdog] ESP32 IDLE but process %s active → re-send SORT_START",
                _current_process_id[0],
            )
            mqtt_client.publish(MQTT_TOPIC_CONTROL, "SORT_START")

    def _check_process_completion(pid: int, p: dict) -> None:
        """분류 수량이 목표에 도달했는지 확인 → 자동 공정 완료."""
        sorted_total = (
            (p.get("success_1l_qty") or 0)
            + (p.get("success_2l_qty") or 0)
            + (p.get("unclassified_qty") or 0)
        )
        order_total = p.get("order_total_qty") or 0
        if order_total <= 0 or sorted_total < order_total:
            return
        # 목표 도달 → 공정 자동 완료
        logger.info("[공정완료] pid=%s sorted=%d/%d", pid, sorted_total, order_total)
        try:
            mqtt_client.publish(MQTT_TOPIC_CONTROL, "SORT_STOP")
            process_stop(int(pid))
        except Exception as e:
            logger.warning("[공정완료] stop error: %s", e)
        _current_process_id[0] = None
        _current_order_items[0] = []
        _stop_udp_camera()
        _reset_monitor()
        _refresh_classify_list()
        _refresh_warehouse_chart()
        worker.classifyResultLabel.setText(
            f"공정 #{pid} 완료! (분류 {sorted_total}/{order_total})"
        )

    def _on_sensor_received(payload: str):
        """device/sensor 수신 → 근접센서 상태 + 분류 결과 처리."""
        # 근접센서 상태
        if payload == "PROXIMITY:1":
            proximity_label.setText("근접센서: 물체감지(동작)!")
            proximity_label.setStyleSheet(
                "font-size: 12px; color: #27ae60; font-weight: bold; border: none;"
            )
            return
        if payload == "PROXIMITY:0":
            proximity_label.setText("근접센서: 감지 되지 않음")
            proximity_label.setStyleSheet(
                "font-size: 12px; color: #8a8a8a; border: none;"
            )
            return

        # 분류 완료 결과
        pid = _current_process_id[0]
        if pid is None:
            return
        p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
        if not p:
            return

        if payload == "SORTED_1L":
            new_qty = (p.get("success_1l_qty") or 0) + 1
            try:
                process_update(int(pid), success_1l_qty=new_qty)
                p["success_1l_qty"] = new_qty
                worker.classifyResultLabel.setText(f"분류 완료: 1L {new_qty}개")
            except Exception as e:
                logger.warning("[MQTT] process_update error (무시): %s", e)
                p["success_1l_qty"] = new_qty
                worker.classifyResultLabel.setText(
                    f"분류 완료: 1L {new_qty}개 (DB 초과)"
                )
            _refresh_classify_list()
            _refresh_warehouse_chart()
            _check_process_completion(pid, p)
        elif payload == "SORTED_2L":
            new_qty = (p.get("success_2l_qty") or 0) + 1
            try:
                process_update(int(pid), success_2l_qty=new_qty)
                p["success_2l_qty"] = new_qty
                worker.classifyResultLabel.setText(f"분류 완료: 2L {new_qty}개")
            except Exception as e:
                logger.warning("[MQTT] process_update error (무시): %s", e)
                p["success_2l_qty"] = new_qty
                worker.classifyResultLabel.setText(
                    f"분류 완료: 2L {new_qty}개 (DB 초과)"
                )
            _refresh_classify_list()
            _refresh_warehouse_chart()
            _check_process_completion(pid, p)
        elif payload == "SORTED_UNCLASSIFIED":
            new_qty = (p.get("unclassified_qty") or 0) + 1
            try:
                process_update(int(pid), unclassified_qty=new_qty)
                p["unclassified_qty"] = new_qty
            except Exception as e:
                logger.warning("[MQTT] process_update error (무시): %s", e)
                p["unclassified_qty"] = new_qty
            # WARNING 레벨 — 공정 정지하지 않음
            worker.classifyResultLabel.setText(f"미분류 감지 ({new_qty}건)")
            warning_label.setText(f"경고: 미분류 물품 감지 ({new_qty}건)")
            warning_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; font-weight: bold; border: none;"
            )
            _refresh_classify_list()
            _refresh_warehouse_chart()
            _check_process_completion(pid, p)

    mqtt_bridge.status_received.connect(_on_status_received)
    mqtt_bridge.sensor_received.connect(_on_sensor_received)

    # ── UDP 카메라 스레드 관리 ─────────────────────────────────────
    _udp_cam_thread: list[UdpCameraThread | None] = [None]

    def _start_udp_camera():
        if _udp_cam_thread[0] and _udp_cam_thread[0].isRunning():
            return
        thread = UdpCameraThread(parent=window)

        def on_frame(qimg: QImage):
            pix = QPixmap.fromImage(qimg)
            cam_preview.setPixmap(
                pix.scaled(
                    cam_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        thread.frame_ready.connect(on_frame)
        thread.qr_decoded.connect(_on_classify_qr_decoded)
        thread.start()
        _udp_cam_thread[0] = thread

    def _stop_udp_camera():
        thread = _udp_cam_thread[0]
        if thread and thread.isRunning():
            thread.stop()
            thread.wait(3000)
        _udp_cam_thread[0] = None
        cam_preview.clear()
        cam_preview.setText("카메라 대기")
        cam_preview.setStyleSheet(
            "background: #222; color: #888; border: 1px solid #555; font-size: 13px;"
        )

    # ── QR 디코딩 결과 처리 (분류 워크플로우) ─────────────────────
    def _on_classify_qr_decoded(data: str):
        """ESP32-CAM QR → 품목 매칭 → UI 표시만 (분류 방향은 esp-devkit이 자체 제어)."""
        payload = _parse_qr_payload(data)
        if not payload:
            qr_status_label.setText("QR 인식: 형식 오류")
            qr_status_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; border: none;"
            )
            logger.warning("[QR] 파싱 실패: %s", data)
            return

        item_code = payload.get("item_code", "")
        order_items = _current_order_items[0]
        logger.info(
            "[QR] item_code=%r, 주문품목=%s",
            item_code,
            [it.get("item_code") for it in order_items],
        )

        if not item_code:
            qr_status_label.setText("QR 인식: item_code 없음")
            qr_status_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; border: none;"
            )
            return

        # 현재 주문 품목에 매칭되는지 확인 (UI 표시만, MQTT SORT_DIR 미발행)
        matched = any(
            (it.get("item_code") or "").strip().lower() == item_code.strip().lower()
            for it in order_items
        )

        if matched:
            code_lower = item_code.strip().lower()
            if code_lower.endswith("_1l"):
                qr_status_label.setText(f"QR 인식: {item_code} (1L)")
                qr_status_label.setStyleSheet(
                    "font-size: 12px; color: #27ae60; font-weight: bold; border: none;"
                )
            elif code_lower.endswith("_2l"):
                qr_status_label.setText(f"QR 인식: {item_code} (2L)")
                qr_status_label.setStyleSheet(
                    "font-size: 12px; color: #27ae60; font-weight: bold; border: none;"
                )
            else:
                qr_status_label.setText(f"QR 인식: {item_code} (용량 불명)")
                qr_status_label.setStyleSheet(
                    "font-size: 12px; color: #f39c12; border: none;"
                )
        else:
            qr_status_label.setText(f"QR 인식: {item_code} (미등록)")
            qr_status_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; font-weight: bold; border: none;"
            )
            warning_label.setText(f"경고: 미등록 품목 ({item_code})")
            warning_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; font-weight: bold; border: none;"
            )

    # ── 모니터 상태 초기화 ─────────────────────────────────────────
    def _reset_monitor():
        _update_fsm_display("IDLE")
        qr_status_label.setText("QR 인식: 대기 중")
        qr_status_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")
        proximity_label.setText("근접센서: 감지 되지 않음")
        proximity_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")
        warning_label.setText("경고: (없음)")
        warning_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")

    # ── 공정 목록 갱신 ─────────────────────────────────────────────

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
        running = next(
            (
                p
                for p in _classify_processes
                if (p.get("status") or "").upper() == "RUNNING"
            ),
            None,
        )
        worker.processTable.setHorizontalHeaderLabels(
            [
                "공정 ID",
                "주문 ID",
                "상태",
                "시작 시각",
                "종료 시각",
                "1L",
                "2L",
                "미분류",
            ]
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
                worker.processTable.setRowHeight(row, 52)
        finally:
            worker.processTable.blockSignals(False)
        # 시각 컬럼·수량 컬럼 너비 고정
        worker.processTable.setColumnWidth(3, 150)
        worker.processTable.setColumnWidth(4, 150)
        worker.processTable.setColumnWidth(5, 50)
        worker.processTable.setColumnWidth(6, 50)
        worker.processTable.setColumnWidth(7, 55)
        worker.processTable.verticalHeader().setDefaultSectionSize(
            52
        )  # 행 높이 (입력란 잘리지 않도록)
        if running:
            worker.label_running_status.setText(
                f"현재 진행 중: 공정 #{running['process_id']} (주문 #{running['order_id']})"
            )
        else:
            worker.label_running_status.setText("현재 진행 중: 없음")
        _classify_update_toggle_button()

    WAREHOUSE_TOTAL = 10  # 창고 현황 총량 기준 (N/10 형식)

    def _refresh_warehouse_chart():
        """공정 목록에서 1L·2L·미분류 합계를 구해 막대 그래프에 반영. 총량 10 기준 N/10 표시."""
        try:
            processes = list_processes()
        except (TimeoutError, OSError, ConnectionError, RuntimeError):
            worker.label_warehouse_1l_count.setText("—")
            worker.label_warehouse_2l_count.setText("—")
            worker.label_warehouse_unclassified_count.setText("—")
            worker.progressBar_1l.setMaximum(WAREHOUSE_TOTAL)
            worker.progressBar_1l.setValue(0)
            worker.progressBar_2l.setMaximum(WAREHOUSE_TOTAL)
            worker.progressBar_2l.setValue(0)
            worker.progressBar_unclassified.setMaximum(WAREHOUSE_TOTAL)
            worker.progressBar_unclassified.setValue(0)
            return
        total_1l = sum(p.get("success_1l_qty", 0) or 0 for p in processes)
        total_2l = sum(p.get("success_2l_qty", 0) or 0 for p in processes)
        total_uncl = sum(p.get("unclassified_qty", 0) or 0 for p in processes)
        worker.label_warehouse_1l_count.setText(f"{total_1l}/{WAREHOUSE_TOTAL}")
        worker.label_warehouse_2l_count.setText(f"{total_2l}/{WAREHOUSE_TOTAL}")
        worker.label_warehouse_unclassified_count.setText(
            f"{total_uncl}/{WAREHOUSE_TOTAL}"
        )
        worker.progressBar_1l.setMaximum(WAREHOUSE_TOTAL)
        worker.progressBar_1l.setValue(min(total_1l, WAREHOUSE_TOTAL))
        worker.progressBar_2l.setMaximum(WAREHOUSE_TOTAL)
        worker.progressBar_2l.setValue(min(total_2l, WAREHOUSE_TOTAL))
        worker.progressBar_unclassified.setMaximum(WAREHOUSE_TOTAL)
        worker.progressBar_unclassified.setValue(min(total_uncl, WAREHOUSE_TOTAL))

    worker.warehouseRefreshButton.clicked.connect(_refresh_warehouse_chart)
    for bar in (
        worker.progressBar_1l,
        worker.progressBar_2l,
        worker.progressBar_unclassified,
    ):
        bar.setTextVisible(False)  # 오른쪽 "N개" 라벨만 표시

    def _classify_update_toggle_button():
        """선택된 공정에 따라 [시작]/[중지] 버튼 문구·활성화."""
        running = next(
            (
                p
                for p in _classify_processes
                if (p.get("status") or "").upper() == "RUNNING"
            ),
            None,
        )
        row = worker.processTable.currentRow()
        item0 = worker.processTable.item(row, 0) if row >= 0 else None
        pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        p = (
            next((x for x in _classify_processes if x.get("process_id") == pid), None)
            if pid is not None
            else None
        )
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

    # ── 공정 시작/중지 통합 ─────────────────────────────────────────

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
                # ── 공정 중지 ──
                process_stop(int(pid))
                mqtt_client.publish(MQTT_TOPIC_CONTROL, "SORT_STOP")
                _current_process_id[0] = None
                _current_order_items[0] = []
                _stop_udp_camera()
                _reset_monitor()
                worker.classifyResultLabel.setText("공정을 중지했습니다.")
            else:
                # ── 공정 시작 ──
                process_start(int(pid))
                _current_process_id[0] = int(pid)

                # 주문 품목 캐시 (list_orders에서 items 포함된 주문 조회)
                order_id = p.get("order_id") if p else None
                if order_id:
                    try:
                        orders = list_orders()
                        order_data = next(
                            (o for o in orders if o.get("order_id") == int(order_id)),
                            None,
                        )
                        _current_order_items[0] = (
                            order_data.get("items") or [] if order_data else []
                        )
                        logger.info(
                            "[공정시작] order_id=%s, 품목=%s",
                            order_id,
                            [it.get("item_code") for it in _current_order_items[0]],
                        )
                    except Exception as e:
                        logger.warning("주문 품목 조회 실패: %s", e)
                        _current_order_items[0] = []
                else:
                    logger.warning("[공정시작] order_id 없음 (process=%s)", pid)
                    _current_order_items[0] = []

                mqtt_client.publish(MQTT_TOPIC_CONTROL, "SORT_START")
                _start_udp_camera()
                _reset_monitor()
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
            p = next(
                (x for x in _classify_processes if x.get("process_id") == pid), None
            )
            old = (
                p.get("success_1l_qty", 0)
                if col == 5
                else (
                    p.get("success_2l_qty", 0)
                    if col == 6
                    else p.get("unclassified_qty", 0)
                )
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText(
                "1L, 2L, 미분류에는 0 이상의 숫자만 입력하세요."
            )
            return
        p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
        if not p:
            return

        # 수정 후 1L+2L+미분류 합이 해당 주문 총량을 넘지 않도록 검사
        def _cell_int(r: int, c: int) -> int:
            it = worker.processTable.item(r, c)
            if not it:
                return 0
            try:
                return int((it.text() or "0").strip())
            except ValueError:
                return 0

        new_1l = val if col == 5 else _cell_int(row, 5)
        new_2l = val if col == 6 else _cell_int(row, 6)
        new_uncl = val if col == 7 else _cell_int(row, 7)
        order_total = p.get("order_total_qty")
        if order_total is not None and (new_1l + new_2l + new_uncl) > order_total:
            worker.processTable.blockSignals(True)
            old = (
                p.get("success_1l_qty", 0)
                if col == 5
                else (
                    p.get("success_2l_qty", 0)
                    if col == 6
                    else p.get("unclassified_qty", 0)
                )
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText(
                f"1L+2L+미분류 합계({new_1l + new_2l + new_uncl})가 해당 주문 총 수량({order_total})을 초과할 수 없습니다."
            )
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
            p = next(
                (x for x in _classify_processes if x.get("process_id") == pid), None
            )
            old = (
                p.get("success_1l_qty", 0)
                if col == 5
                else (
                    p.get("success_2l_qty", 0)
                    if col == 6
                    else p.get("unclassified_qty", 0)
                )
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText(f"저장 실패: {e}")
        except (TimeoutError, OSError, ConnectionError) as e:
            worker.processTable.blockSignals(True)
            p = next(
                (x for x in _classify_processes if x.get("process_id") == pid), None
            )
            old = (
                p.get("success_1l_qty", 0)
                if col == 5
                else (
                    p.get("success_2l_qty", 0)
                    if col == 6
                    else p.get("unclassified_qty", 0)
                )
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

    # ── 화면 전환 시 카메라 정리 ─────────────────────────────────
    def _on_page_leaving():
        _stop_udp_camera()

    def _on_stack_changed(index: int):
        if index != 3:  # page_classify가 아니면 카메라 중지
            _stop_udp_camera()

    stacked.currentChanged.connect(lambda _: _on_page_leaving())
    stack.currentChanged.connect(_on_stack_changed)
