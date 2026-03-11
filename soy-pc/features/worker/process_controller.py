"""
공정 생명주기 제어 — State 디자인패턴 + 독립 분류기 + QR 3단 필터.

아키텍처:
  - ProcessStateBase(states/base.py): 상태 인터페이스
  - IdleState / ActiveState / PausedState: 구체 상태
  - ClassifierBase(classifier.py): 분류 결정 (FSM 무관)
  - QrGate(qr_gate.py): QR 중복 방지 3단 필터 (FSM 무관)
  - ProcessController: 상태 전이 + 이벤트 위임

GUI 코드와 분리. classify_page.py에서 콜백(ProcessCallbacks)으로 UI 업데이트를 위임.
"""

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from mqtt_client import mqtt_client
from api import (
    list_orders,
    list_processes,
    process_start as api_process_start,
    process_stop as api_process_stop,
    process_update as api_process_update,
)
from features.worker.classifier import (
    ClassifierBase,
    SortDirection,
    SuffixClassifier,
)
from features.worker.qr_gate import QrGate, QrRejectReason, MAX_SORT_QUEUE_SIZE

logger = logging.getLogger(__name__)

# ── MQTT 토픽 ──────────────────────────────────────────────────
TOPIC_CONTROL = "device/control"
TOPIC_SENSOR = "device/sensor"
TOPIC_STATUS = "device/status"


# ── 열거형 ─────────────────────────────────────────────────────
class FsmState(str, Enum):
    """ESP32 FSM 상태."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"

    @classmethod
    def from_payload(cls, payload: str) -> "FsmState | None":
        try:
            data = json.loads(payload)
            name = data.get("state", "")
        except (json.JSONDecodeError, AttributeError):
            name = payload.strip()
        try:
            return cls(name)
        except ValueError:
            return None


class SensorEvent(str, Enum):
    """device/sensor 이벤트 타입."""

    PROXIMITY_ON = "PROXIMITY:1"
    PROXIMITY_OFF = "PROXIMITY:0"
    CAMERA_DETECT = "CAMERA_DETECT"
    DETECTED = "DETECTED"
    SORTING_1L = "SORTING_1L"
    SORTING_2L = "SORTING_2L"
    SORTED_1L = "SORTED_1L"
    SORTED_2L = "SORTED_2L"
    SORTED_UNCLASSIFIED = "SORTED_UNCLASSIFIED"
    CAMERA_TIMEOUT = "CAMERA_TIMEOUT"
    SORT_TIMEOUT_1L = "SORT_TIMEOUT:1L"
    SORT_TIMEOUT_2L = "SORT_TIMEOUT:2L"

    @classmethod
    def from_payload(cls, payload: str) -> "SensorEvent | None":
        try:
            return cls(payload)
        except ValueError:
            return None


# ── 콜백 프로토콜 (UI 레이어가 구현) ──────────────────────────
class ProcessCallbacks(Protocol):
    """ProcessController → UI 알림 인터페이스."""

    def on_fsm_state_changed(self, state: FsmState) -> None: ...
    def on_proximity(self, detected: bool) -> None: ...
    def on_detected(self, direction: str, queue_size: int) -> None: ...
    def on_sort_result(self, kind: str, new_qty: int, db_ok: bool) -> None: ...
    def on_unclassified(self, new_qty: int, db_ok: bool) -> None: ...
    def on_process_started(self, pid: int) -> None: ...
    def on_process_paused(self) -> None: ...
    def on_process_resumed(self) -> None: ...
    def on_process_stopped(self, pid: int) -> None: ...
    def on_process_completed(
        self, pid: int, sorted_total: int, order_total: int
    ) -> None: ...
    def on_qr_enqueued(
        self, item_code: str, direction: str, queue_size: int
    ) -> None: ...
    def on_qr_error(self, message: str) -> None: ...
    def on_error(self, message: str) -> None: ...
    def on_sorting_started(self, station: str) -> None: ...
    def on_sorting_ended(self, station: str) -> None: ...
    def on_pending_updated(self, items: list[tuple[str, str]]) -> None: ...
    def on_expected_total_updated(self, count: int) -> None: ...


# ── 공정 상태 구조체 ──────────────────────────────────────────
@dataclass
class ProcessState:
    """현재 진행 중인 공정의 실시간 상태."""

    process_id: int | None = None
    order_items: list[dict] = field(default_factory=list)
    sort_queue: deque[str] = field(default_factory=lambda: deque(maxlen=1))
    process_data: dict | None = None
    pending_items: list[tuple[str, str]] = field(default_factory=list)
    station_1l_active: bool = False
    station_2l_active: bool = False
    expected_total_count: int = 0

    @property
    def is_active(self) -> bool:
        return self.process_id is not None

    def reset(self) -> None:
        """모든 상태 완전 초기화 — CleanShutdown."""
        self.process_id = None
        self.order_items = []
        self.sort_queue.clear()
        self.process_data = None
        self.pending_items = []
        self.station_1l_active = False
        self.station_2l_active = False
        self.expected_total_count = 0


# ── 컨트롤러 ─────────────────────────────────────────────────
class ProcessController:
    """공정 생명주기 관리 — State 디자인패턴.

    이벤트(handle_qr, handle_sensor, handle_status)를
    현재 상태 객체에 위임한다.
    """

    _WATCHDOG_INTERVAL_S = 10.0

    def __init__(
        self,
        callbacks: ProcessCallbacks,
        classifier: ClassifierBase | None = None,
    ) -> None:
        self._cb = callbacks
        self._state = ProcessState()
        self._last_watchdog_ts: float = 0.0

        # 독립 모듈
        self._classifier: ClassifierBase = classifier or SuffixClassifier()
        self._qr_gate = QrGate()

        # State 패턴: 상태 인스턴스 생성
        from features.worker.states import IdleState, ActiveState, PausedState

        self._idle_state = IdleState()
        self._active_state = ActiveState()
        self._paused_state = PausedState()

        # 초기 상태: IDLE
        self._current_state = self._idle_state

    # ── 상태 전이 ─────────────────────────────────────────────

    def _transition_to(self, new_state) -> None:
        """상태 전이. 현재 상태 on_exit → 새 상태 on_enter."""
        logger.info("[State] %s → %s", self._current_state.name, new_state.name)
        self._current_state.on_exit(self)
        self._current_state = new_state
        self._current_state.on_enter(self)

    # ── 속성 ─────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._state.is_active

    @property
    def current_pid(self) -> int | None:
        return self._state.process_id

    @property
    def classifier(self) -> ClassifierBase:
        return self._classifier

    @property
    def order_items(self) -> list[dict]:
        return self._state.order_items

    # ── 공정 시작/중지 ────────────────────────────────────────

    def start(self, process_data: dict) -> None:
        """공정 시작."""
        pid = int(process_data["process_id"])
        try:
            api_process_start(pid)
        except (RuntimeError, TimeoutError, OSError, ConnectionError) as e:
            self._cb.on_error(f"공정 시작 실패: {e}")
            return

        # IDLE → ACTIVE 전이
        self._state.reset()
        self._qr_gate.reset()
        self._state.process_id = pid
        self._state.process_data = process_data

        order_id = process_data.get("order_id")
        if order_id:
            self._state.order_items = self._fetch_order_items(int(order_id))

        self._transition_to(self._active_state)
        mqtt_client.publish(TOPIC_CONTROL, "SORT_START")
        self._cb.on_process_started(pid)
        logger.info("[공정시작] pid=%s", pid)

    def pause(self) -> None:
        """공정 일시정지. 예상 총량·대기 목록 등 상태는 초기화하지 않음."""
        if not self._state.is_active:
            return
        self._transition_to(self._paused_state)
        mqtt_client.publish(TOPIC_CONTROL, "SORT_PAUSE")
        self._cb.on_process_paused()

    def resume(self) -> None:
        """공정 재개."""
        if not self._state.is_active:
            return
        self._transition_to(self._active_state)
        mqtt_client.publish(TOPIC_CONTROL, "SORT_RESUME")
        self._cb.on_process_resumed()

    def stop(self, pid: int | None = None) -> None:
        """공정 수동 중지 — CleanShutdown."""
        target_pid = pid or self._state.process_id
        if target_pid is None:
            return
        try:
            api_process_stop(int(target_pid))
        except (RuntimeError, TimeoutError, OSError, ConnectionError) as e:
            self._cb.on_error(f"공정 중지 실패: {e}")

        mqtt_client.publish(TOPIC_CONTROL, "SORT_STOP")
        self._transition_to(self._idle_state)
        self._cb.on_process_stopped(target_pid)

    def shutdown(self) -> None:
        """프로그램 종료 시 긴급 정리."""
        if self._state.is_active:
            try:
                mqtt_client.publish(TOPIC_CONTROL, "SORT_STOP")
            except Exception:
                pass
        self._state.reset()
        self._qr_gate.reset()

    # ── 이벤트 핸들러 → 현재 상태에 위임 ─────────────────────

    def handle_status(self, payload: str) -> None:
        """device/status → 현재 상태에 위임."""
        self._current_state.handle_status(self, payload)

    def handle_sensor(self, payload: str, processes: list[dict]) -> None:
        """device/sensor → 현재 상태에 위임."""
        self._current_state.handle_sensor(self, payload, processes)

    def handle_qr(self, item_code: str | None) -> None:
        """QR 인식 → 현재 상태에 위임."""
        self._current_state.handle_qr(self, item_code)

    # ── 유틸리티 ──────────────────────────────────────────────

    @staticmethod
    def _fetch_order_items(order_id: int) -> list[dict]:
        """주문 품목 목록 조회."""
        try:
            orders = list_orders()
            order_data = next(
                (o for o in orders if o.get("order_id") == order_id), None
            )
            return order_data.get("items") or [] if order_data else []
        except Exception as e:
            logger.warning("주문 품목 조회 실패: %s", e)
            return []
