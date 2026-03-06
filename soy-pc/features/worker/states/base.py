"""
states/base.py — 공정 상태 기본 인터페이스.

모든 공정 상태(IDLE, ACTIVE, PAUSED)가 구현해야 하는 인터페이스.
ProcessController가 현재 상태에 이벤트를 위임한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from features.worker.process_controller import ProcessController


class ProcessStateBase(ABC):
    """공정 상태 기반 클래스."""

    @abstractmethod
    def on_enter(self, controller: ProcessController) -> None:
        """상태 진입 시 호출."""
        ...

    @abstractmethod
    def on_exit(self, controller: ProcessController) -> None:
        """상태 이탈 시 호출."""
        ...

    @abstractmethod
    def handle_qr(self, controller: ProcessController, item_code: str | None) -> None:
        """QR 인식 결과 처리."""
        ...

    @abstractmethod
    def handle_sensor(
        self, controller: ProcessController, payload: str, processes: list[dict]
    ) -> None:
        """device/sensor 이벤트 처리."""
        ...

    @abstractmethod
    def handle_status(self, controller: ProcessController, payload: str) -> None:
        """device/status 이벤트 처리."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """상태 이름 (디버그용)."""
        ...
