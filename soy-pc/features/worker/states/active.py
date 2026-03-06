"""
states/active.py — ACTIVE 상태 (CONVEYING/CAMERA_HOLD/SORTING 포함).

공정 진행 중. QR 3단 필터 + 독립 분류기 + 센서 이벤트 전 처리.

분류 대기 정리 규칙:
  - SORTED_UNCLASSIFIED 시: 해당 pending 제거 → station 플래그 정리
  - 모든 SORTED_* 후: pending/queue 모두 비어있으면 station 전부 초기화
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
            controller._state.sort_queue.append(SortDirection.WARN.value)
            controller._cb.on_qr_error("item_code 없음")
            return

        # 3단 필터 검사
        reject = controller._qr_gate.try_accept(
            item_code, len(controller._state.sort_queue)
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

        # 큐 + 대기 목록 등록
        controller._state.sort_queue.append(direction.value)
        controller._state.pending_items.append((item_code, direction.value))
        controller._cb.on_pending_updated(list(controller._state.pending_items))

        # ESP32에 방향 전송
        mqtt_client.publish(TOPIC_CONTROL, f"SORT_DIR:{direction.value}")
        logger.info("[QR] SORT_DIR:%s (code=%s)", direction.value, item_code)
        controller._cb.on_qr_enqueued(
            item_code, direction.value, len(controller._state.sort_queue)
        )

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
            return
        elif event == SensorEvent.PROXIMITY_ON:
            controller._cb.on_proximity(True)
        elif event == SensorEvent.PROXIMITY_OFF:
            controller._cb.on_proximity(False)
        elif event == SensorEvent.DETECTED:
            self._handle_detected(controller)
        elif event == SensorEvent.SORTING_1L:
            controller._state.station_1l_active = True
            if controller._state.sort_queue:
                controller._state.sort_queue.popleft()
            controller._cb.on_sorting_started("1L")
        elif event == SensorEvent.SORTING_2L:
            controller._state.station_2l_active = True
            controller._cb.on_sorting_started("2L")
        elif event == SensorEvent.SORTED_1L:
            controller._state.station_1l_active = False
            controller._cb.on_sorting_ended("1L")
            # pending에서 첫 1L 항목 제거
            for i, (code, d) in enumerate(controller._state.pending_items):
                if d == "1L":
                    controller._state.pending_items.pop(i)
                    break
            controller._cb.on_pending_updated(list(controller._state.pending_items))
            self._handle_sort_result(controller, event, processes)
            self._cleanup_if_empty(controller)  # ★ 컨베이어 비었으면 전체 정리
        elif event == SensorEvent.SORTED_2L:
            controller._state.station_2l_active = False
            controller._cb.on_sorting_ended("2L")
            # pending에서 첫 2L 항목 제거
            for i, (code, d) in enumerate(controller._state.pending_items):
                if d == "2L":
                    controller._state.pending_items.pop(i)
                    break
            controller._cb.on_pending_updated(list(controller._state.pending_items))
            self._handle_sort_result(controller, event, processes)
            self._cleanup_if_empty(controller)  # ★ 컨베이어 비었으면 전체 정리
        elif event == SensorEvent.SORTED_UNCLASSIFIED:
            # ★ 미분류: pending 첫 항목 제거 (방향 무관)
            removed_dir = None
            if controller._state.pending_items:
                _, removed_dir = controller._state.pending_items.pop(0)
            controller._cb.on_pending_updated(list(controller._state.pending_items))

            # ★ 해당 방향의 station 플래그도 정리 (서보 타임아웃으로 soy-pc에 정리 알림 없이
            #   물품이 미분류로 빠진 경우, station_active가 True로 잔류하는 버그 방지)
            if removed_dir == "1L" and controller._state.station_1l_active:
                # pending에 다른 1L이 없으면 station 비활성화
                has_more_1l = any(d == "1L" for _, d in controller._state.pending_items)
                if not has_more_1l:
                    controller._state.station_1l_active = False
                    controller._cb.on_sorting_ended("1L")
                    logger.info("[Cleanup] station_1l_active → False (미분류 통과)")
            elif removed_dir == "2L" and controller._state.station_2l_active:
                has_more_2l = any(d == "2L" for _, d in controller._state.pending_items)
                if not has_more_2l:
                    controller._state.station_2l_active = False
                    controller._cb.on_sorting_ended("2L")
                    logger.info("[Cleanup] station_2l_active → False (미분류 통과)")

            self._handle_sort_result(controller, event, processes)
            self._cleanup_if_empty(controller)  # ★ 컨베이어 비었으면 전체 정리

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

    # ── 내부 헬퍼 ────────────────────────────────────────────

    @staticmethod
    def _handle_detected(controller: ProcessController) -> None:
        from features.worker.classifier import SortDirection

        if controller._state.sort_queue:
            direction = controller._state.sort_queue.popleft()
            logger.info(
                "[Queue] DETECTED (남은: %d)", len(controller._state.sort_queue)
            )
        else:
            direction = SortDirection.WARN.value
            logger.warning("[Queue] DETECTED but queue empty")
        controller._cb.on_detected(direction, len(controller._state.sort_queue))

    @staticmethod
    def _cleanup_if_empty(controller: ProcessController) -> None:
        """★ 분류 후 컨베이어에 물품이 없으면 station & pending 전부 초기화.

        조건: pending_items 비어있음 AND sort_queue 비어있음
        → 컨베이어에 물품이 없으므로 모든 표시 초기화.
        이렇게 해야 서보 타임아웃 후 미분류로 빠져도 GUI '분류중' 잔류 방지.
        """
        state = controller._state
        if not state.pending_items and not state.sort_queue:
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
            controller._cb.on_pending_updated([])  # GUI 확실히 비우기

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
            controller._cb.on_unclassified(new_qty, db_ok)
        else:
            kind = "1L" if event == SensorEvent.SORTED_1L else "2L"
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
