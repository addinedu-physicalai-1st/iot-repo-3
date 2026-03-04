"""주문 입고 처리용 QR 스캔 팝업 다이얼로그."""

import json
import logging
from typing import Any, Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from api import order_mark_delivered
from features.worker.threads import CameraQRThread

logger = logging.getLogger(__name__)


# ── QR 페이로드 파싱 ─────────────────────────────────────────────
def parse_qr_payload(data: str) -> dict[str, Any] | None:
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


# ── 입고 스캔 다이얼로그 ─────────────────────────────────────────
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
            payload = parse_qr_payload(data)
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
