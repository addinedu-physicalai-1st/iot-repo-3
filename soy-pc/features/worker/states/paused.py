"""
states/paused.py — PAUSED 상태.

공정 일시정지. QR 거부 (게이트 닫힘), 센서는 제한적 처리.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from features.worker.states.base import ProcessStateBase

if TYPE_CHECKING:
    from features.worker.process_controller import ProcessController

logger = logging.getLogger(__name__)


class PausedState(ProcessStateBase):
    @property
    def name(self) -> str:
        return "PAUSED"

    def on_enter(self, controller: ProcessController) -> None:
        logger.debug("[PausedState] 진입")

    def on_exit(self, controller: ProcessController) -> None:
        pass

    def handle_qr(self, controller: ProcessController, item_code: str | None) -> None:
        # PAUSED 중에는 QR 등록 거부 (QrGate에서도 차단되지만 명시적으로)
        controller._cb.on_qr_error("일시정지 중에는 QR을 등록할 수 없습니다")

    def handle_sensor(
        self, controller: ProcessController, payload: str, processes: list[dict]
    ) -> None:
        from features.worker.process_controller import SensorEvent
        from features.worker.states.active import ActiveState

        event = SensorEvent.from_payload(payload)
        if event is None:
            return
        # PAUSED에서는 근접 센서 + 분류 완료 이벤트 처리
        if event == SensorEvent.PROXIMITY_ON:
            controller._cb.on_proximity(True)
        elif event == SensorEvent.PROXIMITY_OFF:
            controller._cb.on_proximity(False)
        elif event == SensorEvent.S3_DETECTED:
            logger.info("[서보1] 원위치")
            controller._cb.on_center_servo_1l()
            controller._state.station_1l_active = False
            controller._state.current_item = None
            controller._cb.on_current_item_updated(None)
            controller._cb.on_sorting_ended("1L")
            ActiveState._handle_sort_result(controller, event, processes)
            ActiveState._cleanup_if_empty(controller)
        elif event == SensorEvent.S4_DETECTED:
            logger.info("[서보2] 원위치")
            controller._cb.on_center_servo_2l()
            controller._state.station_2l_active = False
            controller._state.current_item = None
            controller._cb.on_current_item_updated(None)
            controller._cb.on_sorting_ended("2L")
            ActiveState._handle_sort_result(controller, event, processes)
            ActiveState._cleanup_if_empty(controller)
        elif event == SensorEvent.S5_DETECTED:
            removed_dir = (
                controller._state.current_item[1]
                if controller._state.current_item
                else None
            )
            controller._state.current_item = None
            controller._cb.on_current_item_updated(None)
            if removed_dir == "1L" and controller._state.station_1l_active:
                controller._state.station_1l_active = False
                controller._cb.on_sorting_ended("1L")
            elif removed_dir == "2L" and controller._state.station_2l_active:
                controller._state.station_2l_active = False
                controller._cb.on_sorting_ended("2L")
            ActiveState._handle_sort_result(controller, event, processes)
            ActiveState._cleanup_if_empty(controller)
        elif event in (SensorEvent.SORT_TIMEOUT_1L, SensorEvent.SORT_TIMEOUT_2L):
            station = "1L" if event == SensorEvent.SORT_TIMEOUT_1L else "2L"
            if station == "1L":
                controller._cb.on_center_servo_1l()
                controller._state.station_1l_active = False
            else:
                controller._cb.on_center_servo_2l()
                controller._state.station_2l_active = False
            controller._state.current_item = None
            controller._cb.on_current_item_updated(None)
            controller._cb.on_sorting_ended(station)
            ActiveState._handle_sort_result(
                controller, SensorEvent.S5_DETECTED, processes
            )
            ActiveState._cleanup_if_empty(controller)
            controller._cb.on_qr_error(
                f"서보 타임아웃 ({station}) — 물리적 이상 감지."
            )

    def handle_status(self, controller: ProcessController, payload: str) -> None:
        from features.worker.process_controller import FsmState

        state = FsmState.from_payload(payload)
        if state:
            controller._cb.on_fsm_state_changed(state)
