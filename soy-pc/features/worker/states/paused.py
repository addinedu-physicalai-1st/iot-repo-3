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

        event = SensorEvent.from_payload(payload)
        if event is None:
            return
        # PAUSED에서는 근접 센서만 추적
        if event == SensorEvent.PROXIMITY_ON:
            controller._cb.on_proximity(True)
        elif event == SensorEvent.PROXIMITY_OFF:
            controller._cb.on_proximity(False)

    def handle_status(self, controller: ProcessController, payload: str) -> None:
        from features.worker.process_controller import FsmState

        state = FsmState.from_payload(payload)
        if state:
            controller._cb.on_fsm_state_changed(state)
