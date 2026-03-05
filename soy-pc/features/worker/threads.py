"""작업자 화면 — 백그라운드 스레드 (카메라, MQTT 브릿지)."""

import logging
import struct

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QImage

from mqtt_client import mqtt_client
from features.worker.process_controller import TOPIC_SENSOR, TOPIC_STATUS

logger = logging.getLogger(__name__)


def _try_decode_qr(pyzbar_mod, cv2, frame):
    """다중 각도 + 전처리로 QR 인식 시도."""
    # 1차: 원본
    results = pyzbar_mod.decode(frame)
    if results:
        return results

    # 2차: 90°, 180°, 270° 회전
    for rot in [cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE]:
        rotated = cv2.rotate(frame, rot)
        results = pyzbar_mod.decode(rotated)
        if results:
            return results

    # 3차: 그레이스케일 + 적응적 이진화
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    results = pyzbar_mod.decode(binary)
    if results:
        return results

    return []


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

                decoded_list = _try_decode_qr(pyzbar_mod, cv2, frame)
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
                        self._last_decoded = qr_data
                        self._cooldown_until = now + 1.0
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

    def reset_cooldown(self):
        """CAMERA_DETECT 수신 시 호출 — 쿨다운 초기화로 즉시 QR 디코딩 가능."""
        self._cooldown_until = 0
        self._last_decoded = None


# ── MQTT → Qt 시그널 브릿지 (스레드 안전) ────────────────────────
class MqttSignalBridge(QObject):
    """paho MQTT 스레드에서 Qt 메인 스레드로 안전하게 신호 전달."""

    sensor_received = pyqtSignal(str)  # device/sensor 페이로드
    status_received = pyqtSignal(str)  # device/status 페이로드

    def __init__(self, parent=None):
        super().__init__(parent)
        mqtt_client.subscribe(TOPIC_SENSOR, self._on_sensor)
        mqtt_client.subscribe(TOPIC_STATUS, self._on_status)

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
