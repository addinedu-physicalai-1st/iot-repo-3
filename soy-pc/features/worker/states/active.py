"""
states/active.py — ACTIVE 상태 (CONVEYING/CAMERA_HOLD/SORTING 포함).

공정 진행 중. QR 3단 필터 + 독립 분류기 + 센서 이벤트 전 처리.

분류 정책: 한 번에 한 개만 (dirQueue 1개).
  - current_item 1개 완료(S3/S4/S5 감지 후 PC 카운팅) 전에는 새 QR 거부.
  - 미분류 카운팅은 S5 감지 시 수행. CAMERA_TIMEOUT 시 current_item으로 등록.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from features.worker.states.base import ProcessStateBase
from features.worker.qr_gate import QrRejectReason, MAX_SORT_QUEUE_SIZE

if TYPE_CHECKING:
    from features.worker.process_controller import ProcessController

logger = logging.getLogger(__name__)

class ActiveState(ProcessStateBase):
    @property
    def name(self) -> str:
        return "ACTIVE"

    def on_enter(self, controller: ProcessController) -> None:
        controller._qr_gate.set_process_active(True)
        logger.debug("[ActiveState] 진입 — QR 게이트 활성화")

    def on_exit(self, controller: ProcessController) -> None:
        pass

    def handle_qr(self, controller: ProcessController, item_code: str | None) -> None:
        """QR 인식 → 3단 필터 → 독립 분류기 → SORT_DIR 발행."""
        from features.worker.classifier import SortDirection
        from mqtt_client import mqtt_client
        from features.worker.process_controller import TOPIC_CONTROL

        if item_code is None or not item_code.strip():
            controller._state.current_item = ("(오류)", SortDirection.WARN.value)
            controller._cb.on_current_item_updated(
                ("(오류)", SortDirection.WARN.value),
            )
            mqtt_client.publish(TOPIC_CONTROL, "SORT_DIR:WARN")
            controller._cb.on_qr_error("item_code 없음")
            return

        # 3단 필터 검사 (한 개 완료 전에는 새 QR 거부)
        reject = controller._qr_gate.try_accept(
            item_code, 1 if controller._state.current_item else 0
        )
        if reject is not None:
            logger.info("[QR] 거부됨: %s (code=%s)", reject.value, item_code)
            if reject == QrRejectReason.QUEUE_FULL:
                controller._cb.on_qr_error(f"대기열 초과 ({MAX_SORT_QUEUE_SIZE}개)")
            return

        # 분류 결정 (독립 분류기)
        direction = controller._classifier.classify(
            item_code, controller._state.order_items
        )

        # QR 게이트 통과 확정
        controller._qr_gate.accept(item_code)

        # 한 개만 유지 (dirQueue와 동일하게 1개)
        controller._state.current_item = (item_code, direction.value)
        controller._cb.on_current_item_updated((item_code, direction.value))

        # ESP32에 방향 전송
        mqtt_client.publish(TOPIC_CONTROL, f"SORT_DIR:{direction.value}")
        logger.info("[QR] SORT_DIR:%s (code=%s)", direction.value, item_code)
        controller._cb.on_qr_enqueued(item_code, direction.value, 1)

    def handle_sensor(
        self, controller: ProcessController, payload: str, processes: list[dict]
    ) -> None:
        from features.worker.process_controller import SensorEvent
        from features.worker.classifier import SortDirection

        event = SensorEvent.from_payload(payload)
        if event is None:
            return

        if event == SensorEvent.CAMERA_DETECT:
            controller._qr_gate.open_camera_gate()
            # 예상 총량: S6(카메라 위치) 감지 시 +1
            controller._state.expected_total_count += 1
            controller._cb.on_expected_total_updated(
                controller._state.expected_total_count
            )
            return
        elif event == SensorEvent.CAMERA_TIMEOUT:
            # QR 미인식 → current_item 등록 (S5 감지 시 미분류 카운팅)
            controller._state.current_item = (
                "(미인식)",
                SortDirection.WARN.value,
            )
            controller._cb.on_current_item_updated(
                ("(미인식)", SortDirection.WARN.value),
            )
            controller._cb.on_qr_error("카메라 타임아웃 — QR 미인식")
            logger.info("[CAMERA_TIMEOUT] QR 미인식 → current_item 등록 (S5 대기)")
            return
        elif event == SensorEvent.PROXIMITY_ON:
            controller._cb.on_proximity(True)
        elif event == SensorEvent.PROXIMITY_OFF:
            controller._cb.on_proximity(False)
        elif event == SensorEvent.S1_DETECTED:
            self._handle_s1_detected(controller)
        elif event == SensorEvent.S2_DETECTED:
            self._handle_s2_detected(controller)
        elif event == SensorEvent.S3_DETECTED:
            logger.info("[서보1] 원위치")
            controller._cb.on_center_servo_1l()
            controller._state.station_1l_active = False
            controller._state.current_item = None
            controller._cb.on_current_item_updated(None)
            controller._cb.on_sorting_ended("1L")
            self._handle_sort_result(controller, event, processes)
            self._cleanup_if_empty(controller)
        elif event == SensorEvent.S4_DETECTED:
            logger.info("[서보2] 원위치")
            controller._cb.on_center_servo_2l()
            controller._state.station_2l_active = False
            controller._state.current_item = None
            controller._cb.on_current_item_updated(None)
            controller._cb.on_sorting_ended("2L")
            self._handle_sort_result(controller, event, processes)
            self._cleanup_if_empty(controller)
        elif event == SensorEvent.S5_DETECTED:
            removed_dir = (
                controller._state.current_item[1]
                if controller._state.current_item
                else None
            )
            if controller._state.current_item:
                logger.info(
                    "[미분류] S5 감지 — 완료: code=%s direction=%s",
                    controller._state.current_item[0],
                    removed_dir,
                )
            controller._state.current_item = None
            controller._cb.on_current_item_updated(None)

            if removed_dir == "1L" and controller._state.station_1l_active:
                controller._cb.on_center_servo_1l()
                controller._state.station_1l_active = False
                controller._cb.on_sorting_ended("1L")
            elif removed_dir == "2L" and controller._state.station_2l_active:
                controller._cb.on_center_servo_2l()
                controller._state.station_2l_active = False
                controller._cb.on_sorting_ended("2L")

            self._handle_sort_result(controller, event, processes)
            self._cleanup_if_empty(controller)
        elif event in (
            SensorEvent.SORT_TIMEOUT_1L,
            SensorEvent.SORT_TIMEOUT_2L,
        ):
            self._handle_sort_timeout(controller, event, processes)

    def handle_status(self, controller: ProcessController, payload: str) -> None:
        from features.worker.process_controller import FsmState, TOPIC_CONTROL
        from mqtt_client import mqtt_client

        state = FsmState.from_payload(payload)
        if state is None:
            return
        controller._cb.on_fsm_state_changed(state)

        if state == FsmState.PAUSED:
            return

        if state == FsmState.RUNNING:
            controller._last_watchdog_ts = 0.0
            return

        # Watchdog
        if state == FsmState.IDLE and controller._state.is_active:
            now = time.monotonic()
            if now - controller._last_watchdog_ts < controller._WATCHDOG_INTERVAL_S:
                return
            controller._last_watchdog_ts = now
            logger.warning("[Watchdog] ESP32 IDLE → re-send SORT_START")
            mqtt_client.publish(TOPIC_CONTROL, "SORT_START")

    def handle_servo_timeout(
        self,
        controller: ProcessController,
        station: str,
        processes: list[dict],
    ) -> None:
        """서보 개방 후 2초 내 카운팅 없음 → 미분류 처리 + 자동 일시정지."""
        from features.worker.process_controller import SensorEvent

        event = (
            SensorEvent.SORT_TIMEOUT_1L
            if station == "1L"
            else SensorEvent.SORT_TIMEOUT_2L
        )
        self._handle_sort_timeout(controller, event, processes)

    # ── 내부 헬퍼 ────────────────────────────────────────────

    @staticmethod
    def _handle_sort_timeout(
        controller: ProcessController, event, processes: list[dict]
    ) -> None:
        """서보 타임아웃 → 미분류 처리 + 자동 일시정지."""
        from features.worker.process_controller import SensorEvent

        station = "1L" if event == SensorEvent.SORT_TIMEOUT_1L else "2L"
        direction = station

        if station == "1L":
            controller._cb.on_center_servo_1l()
            controller._state.station_1l_active = False
        else:
            controller._cb.on_center_servo_2l()
            controller._state.station_2l_active = False
        controller._cb.on_sorting_ended(station)

        controller._state.current_item = None
        controller._cb.on_current_item_updated(None)

        # 미분류 수량 증가 (DB)
        ActiveState._handle_sort_result(
            controller, SensorEvent.S5_DETECTED, processes
        )
        ActiveState._cleanup_if_empty(controller)

        # UI 경고 표시
        controller._cb.on_qr_error(
            f"서보 타임아웃 ({station}) — 물리적 이상 감지. 자동 일시정지합니다."
        )
        logger.warning("[SORT_TIMEOUT] %s — 자동 pause", station)

        # 자동 일시정지
        controller.pause()

    @staticmethod
    def _handle_s1_detected(controller: ProcessController) -> None:
        """S1 감지 — PC가 current_item 기준으로 1L이면 서보A 열기."""
        item = controller._state.current_item
        if not item:
            logger.warning("[S1] 감지됐으나 current_item 없음 (무시)")
            return
        logger.info("[S1] 1L 센서 감지")
        direction = item[1]
        if direction == "1L":
            controller._state.station_1l_active = True
            controller._cb.on_open_servo_1l()
            controller._cb.on_sorting_started("1L")
            logger.info("[서보1] current_item 일치, 분류개방")
        else:
            logger.info("[서보1] current_item 불일치, 분류개방 안함")

    @staticmethod
    def _handle_s2_detected(controller: ProcessController) -> None:
        """S2 감지 — PC가 current_item 기준으로 2L이면 서보B 열기."""
        item = controller._state.current_item
        if not item:
            logger.warning("[S2] 감지됐으나 current_item 없음 (무시)")
            return
        logger.info("[S2] 2L 센서 감지")
        direction = item[1]
        if direction == "2L":
            controller._state.station_2l_active = True
            controller._cb.on_open_servo_2l()
            controller._cb.on_sorting_started("2L")
            logger.info("[서보2] current_item 일치, 분류개방")
        else:
            logger.info("[서보2] current_item 불일치, 분류개방 안함")

    @staticmethod
    def _cleanup_if_empty(controller: ProcessController) -> None:
        """current_item 없으면 station 전부 초기화 (한 개 완료 후)."""
        state = controller._state
        if state.current_item is None:
            changed = False
            if state.station_1l_active:
                state.station_1l_active = False
                controller._cb.on_sorting_ended("1L")
                changed = True
            if state.station_2l_active:
                state.station_2l_active = False
                controller._cb.on_sorting_ended("2L")
                changed = True
            if changed:
                logger.info("[Cleanup] 컨베이어 비어있음 → station 전부 초기화")

    @staticmethod
    def _handle_sort_result(
        controller: ProcessController, event, processes: list[dict]
    ) -> None:
        from features.worker.process_controller import SensorEvent
        from api import (
            process_update as api_process_update,
            process_stop as api_process_stop,
        )
        from mqtt_client import mqtt_client
        from features.worker.process_controller import TOPIC_CONTROL

        pid = controller._state.process_id
        if pid is None:
            return

        p = next((x for x in processes if x.get("process_id") == pid), None)
        if p is None:
            return

        field_map = {
            SensorEvent.S3_DETECTED: "success_1l_qty",
            SensorEvent.S4_DETECTED: "success_2l_qty",
            SensorEvent.S5_DETECTED: "unclassified_qty",
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

        # 카운팅 시점 INFO 로그 (1L / 2L / 미분류)
        kind = (
            "1L"
            if event == SensorEvent.S3_DETECTED
            else ("2L" if event == SensorEvent.S4_DETECTED else "미분류")
        )
        logger.info(
            "[카운팅] pid=%s %s → %d (db_ok=%s)",
            pid,
            kind,
            new_qty,
            db_ok,
        )

        if event == SensorEvent.S5_DETECTED:
            controller._cb.on_unclassified(new_qty, db_ok)
        else:
            kind = "1L" if event == SensorEvent.S3_DETECTED else "2L"
            controller._cb.on_sort_result(kind, new_qty, db_ok)

        # 자동 완료 확인
        sorted_total = (
            (p.get("success_1l_qty") or 0)
            + (p.get("success_2l_qty") or 0)
            + (p.get("unclassified_qty") or 0)
        )
        order_total = p.get("order_total_qty") or 0
        if order_total > 0 and sorted_total >= order_total:
            logger.info("[완료] pid=%s sorted=%d/%d", pid, sorted_total, order_total)
            try:
                mqtt_client.publish(TOPIC_CONTROL, "SORT_STOP")
                api_process_stop(int(pid))
            except Exception as e:
                logger.warning("[완료] stop error: %s", e)
            controller._state.reset()
            controller._qr_gate.reset()
            controller._cb.on_process_completed(pid, sorted_total, order_total)
