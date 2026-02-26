"""
주문(orders) 조회·상태 변경. 입고 시 pending → delivered.
delivered 처리 시 inbounds 1건 추가는 set_order_delivered_and_create_inbound 로 한 트랜잭션 처리.
ORM 사용.
"""
import logging
from datetime import datetime

from sqlalchemy.engine import Engine

from app.database import get_session
from app.models import Inbound, Order, OrderItem

logger = logging.getLogger(__name__)


class OrderNotFound(Exception):
    pass


def get_order(order_id: int, engine: Engine | None = None) -> dict | None:
    """order_id로 주문 조회. 없으면 None."""
    with get_session() as session:
        order = session.get(Order, order_id)
        if not order:
            return None
        return {
            "order_id": order.order_id,
            "order_date": order.order_date.isoformat() if order.order_date else "",
            "status": (order.status or "").strip().upper(),
        }


def get_order_id_by_order_item_id(order_item_id: int, engine: Engine | None = None) -> int | None:
    """order_item_id로 order_id 조회. 없으면 None."""
    with get_session() as session:
        item = session.get(OrderItem, order_item_id)
        return int(item.order_id) if item else None


def set_order_delivered(order_id: int, engine: Engine | None = None) -> str | None:
    """
    주문 상태를 DELIVERED로 변경.
    이미 DELIVERED면 에러 메시지 반환. 없으면 OrderNotFound.
    성공 시 None.
    """
    with get_session() as session:
        order = session.get(Order, order_id)
        if not order:
            raise OrderNotFound()
        if (order.status or "").strip().upper() == "DELIVERED":
            return "이미 입고한 주문입니다."
        order.status = "DELIVERED"
    return None


def set_order_delivered_and_create_inbound(
    order_id: int, engine: Engine | None = None
) -> tuple[str | None, str | None]:
    """
    주문을 DELIVERED로 바꾸고 inbounds에 1건 추가. 한 트랜잭션으로 처리하며,
    inbound INSERT 실패 시 orders 변경도 롤백되어 PENDING 유지.

    트랜잭션 경계: 아래 with get_session() 블록 전체가 하나의 트랜잭션.
    - 블록 안의 order UPDATE와 inbound INSERT는 같은 session에서 실행됨.
    - 블록 정상 종료 시 get_session()이 commit() 한 번 호출 → 둘 다 반영.
    - 블록 안에서 예외 시 get_session()이 rollback() → 둘 다 취소.

    반환: (에러 메시지, inbound_id). 성공 시 (None, inbound_id), 실패 시 (에러문구, None).
    없으면 OrderNotFound.
    """
    with get_session() as session:  # 트랜잭션 시작 (commit/rollback은 get_session이 처리)
        order = session.get(Order, order_id)
        if not order:
            raise OrderNotFound()
        if (order.status or "").strip().upper() == "DELIVERED":
            return ("이미 입고한 주문입니다.", None)
        now = datetime.utcnow()
        inbound_id = f"IN-{order_id}-{now.strftime('%Y%m%d%H%M%S')}"
        order.status = "DELIVERED"
        session.flush()
        inbound = Inbound(
            inbound_id=inbound_id,
            order_id=order_id,
            inbound_date=now,
            status="WAITING",
        )
        session.add(inbound)
        session.flush()
        # 여기서 with 블록 종료 → get_session()이 commit() 호출 → order UPDATE + inbound INSERT 한 번에 반영
    logger.info("order_id=%s delivered, inbound_id=%s", order_id, inbound_id)
    return (None, inbound_id)
