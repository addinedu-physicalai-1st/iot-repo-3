"""
qr_gate.py — QR 중복 인식 방지 3단 필터.

3단 필터 체인:
  ① 최소 대기시간 게이트  — 마지막 등록 후 MIN_QR_INTERVAL_S 이내이면 거부
  ② 물리적 위치 게이트   — ESP32 CAMERA_DETECT 이벤트 이후에만 QR 처리 허용
  ③ 동일 QR 연속 차단   — 같은 item_code가 연속이면 거부 (CAMERA_DETECT 리셋)

이 모듈은 FSM, MQTT, UI 어디에도 의존하지 않는다.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ── 설정 상수 ────────────────────────────────────────────────
MIN_QR_INTERVAL_S: float = 1.5  # QR 등록 최소 간격 (초)
MAX_SORT_QUEUE_SIZE: int = 1  # 분류 큐 최대 크기 (1개만 유지, 새 항목 시 대체)


class QrRejectReason(str, Enum):
    """QR 거부 사유."""

    COOLDOWN = "최소 대기시간 미달"
    GATE_CLOSED = "카메라 위치 게이트 닫힘"
    DUPLICATE = "동일 QR 연속 인식"
    QUEUE_FULL = "분류 대기열 초과"
    PROCESS_INACTIVE = "공정 미활성"


@dataclass
class QrGate:
    """QR 중복 인식 방지 3단 필터.

    사용법:
        gate = QrGate()
        gate.open_camera_gate()       # CAMERA_DETECT 수신 시
        result = gate.try_accept(code, queue_size)
        if result is None: 통과
        else: result == QrRejectReason
    """

    _last_enqueue_ts: float = 0.0
    _last_registered_code: str | None = None
    _camera_gate_open: bool = False
    _process_active: bool = False

    def try_accept(
        self, item_code: str, current_queue_size: int
    ) -> QrRejectReason | None:
        """QR 코드를 3단 필터로 검사한다. None이면 통과, 아니면 거부 사유 반환."""

        # 0. 공정 활성 확인
        if not self._process_active:
            return QrRejectReason.PROCESS_INACTIVE

        now = time.monotonic()

        # ① 최소 대기시간 게이트
        if now - self._last_enqueue_ts < MIN_QR_INTERVAL_S:
            logger.debug(
                "[QrGate] REJECT: cooldown (%.1fs)", now - self._last_enqueue_ts
            )
            return QrRejectReason.COOLDOWN

        # ② 물리적 위치 게이트 (CAMERA_DETECT 이후에만 허용)
        if not self._camera_gate_open:
            logger.debug("[QrGate] REJECT: camera gate closed")
            return QrRejectReason.GATE_CLOSED

        # ③ 동일 QR 연속 차단
        code = item_code.strip().lower() if item_code else ""
        if code and code == (self._last_registered_code or "").strip().lower():
            logger.debug("[QrGate] REJECT: duplicate '%s'", code)
            return QrRejectReason.DUPLICATE

        # ④ 한 번에 한 개만: 이미 1개 처리 중이면 새 QR 거부 (완료 후에만 다음 허용)
        if current_queue_size >= MAX_SORT_QUEUE_SIZE:
            logger.warning("[QrGate] REJECT: queue full (%d)", current_queue_size)
            return QrRejectReason.QUEUE_FULL

        return None  # 통과

    def accept(self, item_code: str) -> None:
        """QR 통과 확정 후 상태 갱신. try_accept 통과 후 반드시 호출."""
        self._last_enqueue_ts = time.monotonic()
        self._last_registered_code = item_code.strip().lower() if item_code else None
        self._camera_gate_open = False  # 게이트 닫기 (다음 CAMERA_DETECT까지)
        logger.info("[QrGate] ACCEPTED: '%s'", item_code)

    def open_camera_gate(self) -> None:
        """CAMERA_DETECT 수신 시 호출 — 게이트 열기 + 동일 QR 차단 해제."""
        self._camera_gate_open = True
        self._last_registered_code = None
        logger.debug("[QrGate] Camera gate OPENED")

    def set_process_active(self, active: bool) -> None:
        """공정 시작/종료 시 호출."""
        self._process_active = active
        if not active:
            self.reset()

    def reset(self) -> None:
        """모든 상태 초기화. 공정 종료/정지/종료 시 호출."""
        self._last_enqueue_ts = 0.0
        self._last_registered_code = None
        self._camera_gate_open = False
        self._process_active = False
        logger.debug("[QrGate] RESET")
