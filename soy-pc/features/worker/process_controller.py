"""
공정 생명주기 제어 — MQTT 명령 발행 + TCP DB 업데이트 + 자동 완료 판단.

GUI 코드와 분리된 비즈니스 로직 전담 모듈.
worker_screen.py 에서 콜백(ProcessCallbacks)으로 UI 업데이트를 위임한다.
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


class SortDirection(str, Enum):
    """분류 방향."""

    LINE_1L = "1L"
    LINE_2L = "2L"
    WARN = "WARN"


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


# ── 공정 상태 구조체 ──────────────────────────────────────────
@dataclass
class ProcessState:
    """현재 진행 중인 공정의 실시간 상태."""

    process_id: int | None = None
    order_items: list[dict] = field(default_factory=list)
    sort_queue: deque[str] = field(default_factory=deque)
    process_data: dict | None = None  # 서버에서 가져온 공정 dict 캐시
    pending_items: list[tuple[str, str]] = field(default_factory=list)  # (item_code, direction)
    station_1l_active: bool = False
    station_2l_active: bool = False

    @property
    def is_active(self) -> bool:
        return self.process_id is not None

    def reset(self) -> None:
        self.process_id = None
        self.order_items = []
        self.sort_queue.clear()
        self.process_data = None
        self.pending_items = []
        self.station_1l_active = False
        self.station_2l_active = False


# ── 컨트롤러 ─────────────────────────────────────────────────
class ProcessController:
    """공정 생명주기 관리 — GUI와 분리된 비즈니스 로직."""

    _WATCHDOG_INTERVAL_S = 10.0  # Watchdog 최소 재전송 간격

    def __init__(self, callbacks: ProcessCallbacks) -> None:
        self._cb = callbacks
        self._state = ProcessState()
        self._last_watchdog_ts: float = 0.0
        self._qr_gate_open: bool = False

    # ── 공정 시작/중지 ────────────────────────────────────────

    def start(self, process_data: dict) -> None:
        """공정 시작. process_data는 서버에서 가져온 공정 dict."""
        pid = int(process_data["process_id"])
        try:
            api_process_start(pid)
        except (RuntimeError, TimeoutError, OSError, ConnectionError) as e:
            self._cb.on_error(f"공정 시작 실패: {e}")
            return

        self._state.reset()
        self._state.process_id = pid
        self._state.process_data = process_data
        self._qr_gate_open = False

        # 주문 품목 캐시
        order_id = process_data.get("order_id")
        if order_id:
            self._state.order_items = self._fetch_order_items(int(order_id))

        mqtt_client.publish(TOPIC_CONTROL, "SORT_START")
        self._cb.on_process_started(pid)
        logger.info(
            "[공정시작] pid=%s, items=%s",
            pid,
            [it.get("item_code") for it in self._state.order_items],
        )

    def pause(self) -> None:
        """공정 일시정지. DB 상태는 RUNNING 유지, ESP32만 PAUSED."""
        if not self._state.is_active:
            return
        mqtt_client.publish(TOPIC_CONTROL, "SORT_PAUSE")
        self._cb.on_process_paused()
        logger.info("[공정일시정지] pid=%s", self._state.process_id)

    def resume(self) -> None:
        """공정 재개. ESP32 → RUNNING 복귀."""
        if not self._state.is_active:
            return
        mqtt_client.publish(TOPIC_CONTROL, "SORT_RESUME")
        self._cb.on_process_resumed()
        logger.info("[공정재개] pid=%s", self._state.process_id)

    def stop(self, pid: int | None = None) -> None:
        """공정 수동 중지. pid가 없으면 현재 진행 중인 공정을 중지."""
        target_pid = pid or self._state.process_id
        if target_pid is None:
            return
        try:
            api_process_stop(int(target_pid))
        except (RuntimeError, TimeoutError, OSError, ConnectionError) as e:
            self._cb.on_error(f"공정 중지 실패: {e}")

        mqtt_client.publish(TOPIC_CONTROL, "SORT_STOP")
        self._state.reset()
        self._cb.on_process_stopped(target_pid)

    @property
    def is_active(self) -> bool:
        return self._state.is_active

    @property
    def current_pid(self) -> int | None:
        return self._state.process_id

    # ── MQTT 이벤트 핸들러 ────────────────────────────────────

    def handle_status(self, payload: str) -> None:
        """device/status 수신 처리."""
        state = FsmState.from_payload(payload)
        if state is None:
            return
        self._cb.on_fsm_state_changed(state)

        # PAUSED 상태에서는 Watchdog 비활성화
        if state == FsmState.PAUSED:
            return

        # RUNNING 수신 → watchdog 타이머 리셋
        if state == FsmState.RUNNING:
            self._last_watchdog_ts = 0.0
            return

        # Watchdog: ESP32 IDLE인데 공정 진행 중이면 SORT_START 재전송 (쓰로틀링)
        if state == FsmState.IDLE and self._state.is_active:
            now = time.monotonic()
            if now - self._last_watchdog_ts < self._WATCHDOG_INTERVAL_S:
                return
            self._last_watchdog_ts = now
            logger.warning(
                "[Watchdog] ESP32 IDLE but process %s active → re-send SORT_START",
                self._state.process_id,
            )
            mqtt_client.publish(TOPIC_CONTROL, "SORT_START")

    def handle_sensor(self, payload: str, processes: list[dict]) -> None:
        """device/sensor 수신 처리."""
        event = SensorEvent.from_payload(payload)
        if event is None:
            return

        if event == SensorEvent.CAMERA_DETECT:
            self._qr_gate_open = True
            return
        elif event == SensorEvent.PROXIMITY_ON:
            self._cb.on_proximity(True)
        elif event == SensorEvent.PROXIMITY_OFF:
            self._cb.on_proximity(False)
        elif event == SensorEvent.DETECTED:
            self._handle_detected()
        elif event == SensorEvent.SORTING_1L:
            self._state.station_1l_active = True
            self._cb.on_sorting_started("1L")
        elif event == SensorEvent.SORTING_2L:
            self._state.station_2l_active = True
            self._cb.on_sorting_started("2L")
        elif event == SensorEvent.SORTED_1L:
            self._state.station_1l_active = False
            self._cb.on_sorting_ended("1L")
            # pending에서 첫 1L 항목 제거
            for i, (code, d) in enumerate(self._state.pending_items):
                if d == "1L":
                    self._state.pending_items.pop(i)
                    break
            self._cb.on_pending_updated(list(self._state.pending_items))
            self._handle_sort_result(event, processes)
        elif event == SensorEvent.SORTED_2L:
            self._state.station_2l_active = False
            self._cb.on_sorting_ended("2L")
            # pending에서 첫 2L 항목 제거
            for i, (code, d) in enumerate(self._state.pending_items):
                if d == "2L":
                    self._state.pending_items.pop(i)
                    break
            self._cb.on_pending_updated(list(self._state.pending_items))
            self._handle_sort_result(event, processes)
        elif event == SensorEvent.SORTED_UNCLASSIFIED:
            # pending에서 첫 항목 제거 (방향 무관)
            if self._state.pending_items:
                self._state.pending_items.pop(0)
                self._cb.on_pending_updated(list(self._state.pending_items))
            self._handle_sort_result(event, processes)

    def handle_qr(self, item_code: str | None) -> None:
        """QR 인식 결과 → 즉시 SORT_DIR 발행 + 큐 기록 + 대기 목록 갱신.
        CAMERA_DETECT 수신 후 1회만 처리 (게이트 방식)."""
        if not self._qr_gate_open:
            logger.debug("[QR] Gate closed, ignoring: %s", item_code)
            return
        self._qr_gate_open = False  # 1회 처리 후 게이트 닫기

        if item_code is None or not item_code.strip():
            self._state.sort_queue.append(SortDirection.WARN.value)
            self._cb.on_qr_error("item_code 없음")
            return

        direction = self._resolve_direction(item_code)
        self._state.sort_queue.append(direction.value)
        # 대기 목록에 추가
        self._state.pending_items.append((item_code, direction.value))
        self._cb.on_pending_updated(list(self._state.pending_items))
        # S1/S2 감지 전 예약: 즉시 ESP32에 방향 전송
        mqtt_client.publish(TOPIC_CONTROL, f"SORT_DIR:{direction.value}")
        logger.info("[QR] SORT_DIR:%s 즉시 전송", direction.value)
        self._cb.on_qr_enqueued(item_code, direction.value, len(self._state.sort_queue))

    # ── 내부 로직 ────────────────────────────────────────────

    def _handle_detected(self) -> None:
        """S1/S2 감지 → 큐 소비 + UI 업데이트. SORT_DIR은 handle_qr()에서 이미 전송됨."""
        if self._state.sort_queue:
            direction = self._state.sort_queue.popleft()
            logger.info(
                "[Queue] DETECTED (남은: %d)",
                len(self._state.sort_queue),
            )
        else:
            direction = SortDirection.WARN.value
            logger.warning("[Queue] DETECTED but queue empty")

        self._cb.on_detected(direction, len(self._state.sort_queue))

    def _handle_sort_result(self, event: SensorEvent, processes: list[dict]) -> None:
        """분류 확인 센서 이벤트 → DB 업데이트 + 자동 완료 확인."""
        pid = self._state.process_id
        if pid is None:
            return

        p = next((x for x in processes if x.get("process_id") == pid), None)
        if p is None:
            return

        field_map = {
            SensorEvent.SORTED_1L: "success_1l_qty",
            SensorEvent.SORTED_2L: "success_2l_qty",
            SensorEvent.SORTED_UNCLASSIFIED: "unclassified_qty",
        }
        field_name = field_map.get(event)
        if field_name is None:
            return

        new_qty = (p.get(field_name) or 0) + 1
        db_ok = True
        try:
            api_process_update(int(pid), **{field_name: new_qty})
        except Exception as e:
            logger.warning("[Controller] process_update error: %s", e)
            db_ok = False
        p[field_name] = new_qty

        if event == SensorEvent.SORTED_UNCLASSIFIED:
            self._cb.on_unclassified(new_qty, db_ok)
        else:
            kind = "1L" if event == SensorEvent.SORTED_1L else "2L"
            self._cb.on_sort_result(kind, new_qty, db_ok)

        self._check_completion(pid, p)

    def _check_completion(self, pid: int, p: dict) -> None:
        """분류 합계가 주문 수량에 도달하면 자동 공정 완료."""
        sorted_total = (
            (p.get("success_1l_qty") or 0)
            + (p.get("success_2l_qty") or 0)
            + (p.get("unclassified_qty") or 0)
        )
        order_total = p.get("order_total_qty") or 0
        if order_total <= 0 or sorted_total < order_total:
            return

        logger.info("[공정완료] pid=%s sorted=%d/%d", pid, sorted_total, order_total)
        try:
            mqtt_client.publish(TOPIC_CONTROL, "SORT_STOP")
            api_process_stop(int(pid))
        except Exception as e:
            logger.warning("[공정완료] stop error: %s", e)

        self._state.reset()
        self._cb.on_process_completed(pid, sorted_total, order_total)

    def _resolve_direction(self, item_code: str) -> SortDirection:
        """item_code + 주문 품목으로 분류 방향 결정."""
        order_items = self._state.order_items
        code_lower = item_code.strip().lower()

        matched = any(
            (it.get("item_code") or "").strip().lower() == code_lower
            for it in order_items
        )
        if not matched:
            return SortDirection.WARN

        if code_lower.endswith("_1l"):
            return SortDirection.LINE_1L
        elif code_lower.endswith("_2l"):
            return SortDirection.LINE_2L
        else:
            return SortDirection.WARN

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
