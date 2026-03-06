"""
classifier.py — 분류 결정 독립 모듈 (Strategy Pattern).

FSM 상태, MQTT, 센서 어디에도 의존하지 않는다.
분류 규칙 변경 시 ClassifierBase 구현체만 교체하면 된다.
"""

from abc import ABC, abstractmethod
from enum import Enum


class SortDirection(str, Enum):
    """분류 방향."""

    LINE_1L = "1L"
    LINE_2L = "2L"
    WARN = "WARN"


class ClassifierBase(ABC):
    """분류 결정 인터페이스. FSM 상태에 무관하게 독립적으로 동작."""

    @abstractmethod
    def classify(self, item_code: str, order_items: list[dict]) -> SortDirection:
        """item_code와 주문 품목을 기반으로 분류 방향을 결정한다."""
        ...


class SuffixClassifier(ClassifierBase):
    """item_code의 suffix(_1l, _2l)로 분류 방향을 결정하는 기본 분류기."""

    def classify(self, item_code: str, order_items: list[dict]) -> SortDirection:
        code_lower = item_code.strip().lower()

        # 주문 품목에 존재하는지 확인
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
