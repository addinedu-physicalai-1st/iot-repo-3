"""작업자 화면 — 돌아가기, 주문 관리(송장 QR 스캔 → 주문 delivered, inbound 기록)."""
import json
import logging
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFrame

from api import order_mark_delivered

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
            stack.setCurrentIndex(1)  # page_inbound
        else:
            stack.setCurrentIndex(0)  # page_welcome

    worker.menu_inbound.clicked.connect(on_menu_inbound_clicked)

    # ----- 주문 관리 페이지: 카메라 + 송장 QR 스캔 -----
    camera_thread: CameraQRThread | None = None
    scan_active = False

    def on_scan_toggle():
        nonlocal camera_thread, scan_active
        if scan_active:
            if camera_thread and camera_thread.isRunning():
                camera_thread.stop()
                camera_thread.wait(3000)
            worker.cameraPreview.clear()
            worker.cameraPreview.setText("카메라 미리보기")
            worker.scanToggleButton.setText("QR 스캔 시작")
            worker.inboundResultLabel.setText(
                "송장 QR을 카메라에 비춰 주세요. 스캔 시작 버튼을 누른 뒤 QR을 인식하면 자동으로 입고 처리됩니다."
            )
            scan_active = False
            return
        # 시작
        try:
            camera_thread = CameraQRThread(worker)
        except Exception as e:
            worker.inboundResultLabel.setText(f"카메라를 사용할 수 없습니다: {e}")
            return

        def on_frame(qimg: QImage):
            pix = QPixmap.fromImage(qimg)
            worker.cameraPreview.setPixmap(
                pix.scaled(
                    worker.cameraPreview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        def on_qr(data: str):
            payload = _parse_qr_payload(data)
            if not payload:
                worker.inboundResultLabel.setText("인식된 QR 형식을 처리할 수 없습니다.")
                return
            order_id = payload.get("order_id")
            order_item_id = payload.get("order_item_id")
            if order_id is None and order_item_id is None:
                worker.inboundResultLabel.setText("QR에 주문 정보가 없습니다. (order_id 또는 order_item_id 필요)")
                return
            try:
                if order_id is not None:
                    order_mark_delivered(order_id=int(order_id))
                else:
                    order_mark_delivered(order_item_id=int(order_item_id))
                worker.inboundResultLabel.setText("입고 처리되었습니다.")
            except RuntimeError as e:
                err = str(e)
                if "이미 입고한" in err:
                    worker.inboundResultLabel.setText("이미 입고한 주문입니다.")
                else:
                    worker.inboundResultLabel.setText(f"처리 실패: {err}")
            except (TimeoutError, OSError, ConnectionError) as e:
                worker.inboundResultLabel.setText(f"서버 연결 실패. 서버가 실행 중인지 확인하세요.\n{e!s}")

        camera_thread.frame_ready.connect(on_frame)
        camera_thread.qr_decoded.connect(on_qr)
        camera_thread.start()
        worker.scanToggleButton.setText("QR 스캔 중지")
        worker.inboundResultLabel.setText("QR을 카메라에 비춰 주세요…")
        scan_active = True

    worker.scanToggleButton.clicked.connect(on_scan_toggle)

    def stop_camera_if_leaving():
        nonlocal scan_active, camera_thread
        try:
            if stacked.currentWidget() is not worker and scan_active:
                if camera_thread and camera_thread.isRunning():
                    camera_thread.stop()
                    camera_thread.wait(2000)
                scan_active = False
        except Exception:
            pass

    def stop_camera_if_switching_to_welcome(index: int):
        nonlocal scan_active, camera_thread
        if index != 1 and scan_active:  # 1 = page_inbound
            try:
                if camera_thread and camera_thread.isRunning():
                    camera_thread.stop()
                    camera_thread.wait(2000)
                scan_active = False
                worker.cameraPreview.clear()
                worker.cameraPreview.setText("카메라 미리보기")
                worker.scanToggleButton.setText("QR 스캔 시작")
                worker.inboundResultLabel.setText(
                    "송장 QR을 카메라에 비춰 주세요. 스캔 시작 버튼을 누른 뒤 QR을 인식하면 자동으로 입고 처리됩니다."
                )
            except Exception:
                pass

    stacked.currentChanged.connect(lambda _: stop_camera_if_leaving())
    stack.currentChanged.connect(stop_camera_if_switching_to_welcome)
