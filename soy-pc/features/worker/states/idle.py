"""
states/idle.py — IDLE 상태.

공정 미활성. QR 거부, 센서 무시.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from features.worker.states.base import ProcessStateBase

if TYPE_CHECKING:
    from features.worker.process_controller import ProcessController

logger = logging.getLogger(__name__)


class IdleState(ProcessStateBase):
    @property
    def name(self) -> str:
        return "IDLE"

    def on_enter(self, controller: ProcessController) -> None:
        """모든 잔여 데이터 초기화 (CleanShutdown)."""
        controller._state.reset()
        controller._qr_gate.reset()
        logger.debug("[IdleState] 진입 — 모든 데이터 초기화")

    def on_exit(self, controller: ProcessController) -> None:
        pass

    def handle_qr(self, controller: ProcessController, item_code: str | None) -> None:
        controller._cb.on_qr_error("공정이 시작되지 않았습니다")

    def handle_sensor(
        self, controller: ProcessController, payload: str, processes: list[dict]
    ) -> None:
        pass  # IDLE에서는 센서 무시

    def handle_status(self, controller: ProcessController, payload: str) -> None:
        from features.worker.process_controller import FsmState

        state = FsmState.from_payload(payload)
        if state:
            controller._cb.on_fsm_state_changed(state)
