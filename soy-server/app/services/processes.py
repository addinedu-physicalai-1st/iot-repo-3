"""
공정(processes) 조회·시작·중지.
한 번에 하나의 공정만 RUNNING. 시작 시 기존 RUNNING은 PAUSED로 전환.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.engine import Engine

from app.database import get_session
from app.models import Order, Process

logger = logging.getLogger(__name__)

RUNNING = "RUNNING"
PAUSED = "PAUSED"
NOT_STARTED = "NOT_STARTED"


def list_processes(engine: Engine | None = None) -> list[dict[str, Any]]:
    """process_id 내림차순(최신 먼저)으로 공정 목록 반환.
    order_total_qty: 해당 주문(order_id)의 items 총 수량(1L+2L+미분류 상한)."""
    with get_session() as session:
        stmt = select(Process).order_by(desc(Process.process_id))
        rows = session.execute(stmt).scalars().all()
        result = []
        for p in rows:
            order = session.get(Order, p.order_id)
            order_total_qty = (
                sum(oi.expected_qty or 0 for oi in order.order_items) if order else 0
            )
            result.append(
                {
                    "process_id": p.process_id,
                    "order_id": p.order_id,
                    "start_time": p.start_time.isoformat() if p.start_time else None,
                    "end_time": p.end_time.isoformat() if p.end_time else None,
                    "status": (p.status or "").strip().upper(),
                    "total_qty": p.total_qty,
                    "success_1l_qty": p.success_1l_qty,
                    "success_2l_qty": p.success_2l_qty,
                    "unclassified_qty": p.unclassified_qty,
                    "order_total_qty": order_total_qty,
                }
            )
        return result


class ProcessNotFound(Exception):
    pass


class ProcessQtyExceedsOrderTotal(Exception):
    """1L+2L+미분류 합계가 해당 주문의 items 총량을 초과할 때."""

    def __init__(self, order_id: int, order_total: int, requested_total: int):
        self.order_id = order_id
        self.order_total = order_total
        self.requested_total = requested_total
        super().__init__(
            f"1L+2L+미분류 합계({requested_total})가 주문 #{order_id} 총 수량({order_total})을 초과할 수 없습니다."
        )


def _get_running_process(session) -> Process | None:
    stmt = select(Process).where(Process.status == RUNNING).limit(1)
    return session.execute(stmt).scalars().first()


def start_process(process_id: int, engine: Engine | None = None) -> dict[str, Any]:
    """
    공정 시작. start_time 설정, status=RUNNING.
    이미 다른 공정이 RUNNING이면 해당 공정을 PAUSED + end_time 설정 후 선택 공정 시작.
    """
    with get_session() as session:
        process = session.get(Process, process_id)
        if not process:
            raise ProcessNotFound()
        now = datetime.utcnow()
        # 다른 RUNNING 공정이 있으면 먼저 중지
        running = _get_running_process(session)
        if running and running.process_id != process_id:
            running.status = PAUSED
            running.end_time = now
            logger.info(
                "process_id=%s auto-paused (another process starting)",
                running.process_id,
            )
        process.start_time = process.start_time or now
        process.status = RUNNING
        process.end_time = None
        session.flush()
        logger.info("process_id=%s started", process_id)
        return {
            "process_id": process.process_id,
            "order_id": process.order_id,
            "start_time": (
                process.start_time.isoformat() if process.start_time else None
            ),
            "status": process.status,
        }


def stop_process(process_id: int, engine: Engine | None = None) -> dict[str, Any]:
    """공정 중지. end_time 설정, status=PAUSED."""
    with get_session() as session:
        process = session.get(Process, process_id)
        if not process:
            raise ProcessNotFound()
        now = datetime.utcnow()
        process.status = PAUSED
        process.end_time = now
        session.flush()
        logger.info("process_id=%s stopped", process_id)
        return {
            "process_id": process.process_id,
            "end_time": process.end_time.isoformat() if process.end_time else None,
            "status": process.status,
        }


def update_process(
    process_id: int,
    *,
    success_1l_qty: int | None = None,
    success_2l_qty: int | None = None,
    unclassified_qty: int | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """공정 수량(1L, 2L, 미분류)만 갱신. None인 필드는 변경하지 않음.
    갱신 후 1L+2L+미분류 합계가 해당 주문(order_id)의 items 총량을 초과하면 ProcessQtyExceedsOrderTotal."""
    with get_session() as session:
        process = session.get(Process, process_id)
        if not process:
            raise ProcessNotFound()
        if success_1l_qty is not None:
            process.success_1l_qty = max(0, success_1l_qty)
        if success_2l_qty is not None:
            process.success_2l_qty = max(0, success_2l_qty)
        if unclassified_qty is not None:
            process.unclassified_qty = max(0, unclassified_qty)
        session.flush()

        # 해당 주문의 items 총량 초과 여부 검사
        order = session.get(Order, process.order_id)
        if order:
            order_total = sum(oi.expected_qty or 0 for oi in order.order_items)
            classified_total = (
                process.success_1l_qty
                + process.success_2l_qty
                + process.unclassified_qty
            )
            if classified_total > order_total:
                raise ProcessQtyExceedsOrderTotal(
                    order_id=process.order_id,
                    order_total=order_total,
                    requested_total=classified_total,
                )

        logger.info(
            "process_id=%s updated 1l=%s 2l=%s uncl=%s",
            process_id,
            process.success_1l_qty,
            process.success_2l_qty,
            process.unclassified_qty,
        )
        return {
            "process_id": process.process_id,
            "success_1l_qty": process.success_1l_qty,
            "success_2l_qty": process.success_2l_qty,
            "unclassified_qty": process.unclassified_qty,
        }
