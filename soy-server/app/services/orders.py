"""
주문(orders) 조회·상태 변경. 입고 시 pending → delivered.
delivered 처리 시 processes 1건 추가는 set_order_delivered_and_create_process 로 한 트랜잭션 처리.
ORM 사용.
"""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import get_session
from app.models import Order, OrderItem, Process

logger = logging.getLogger(__name__)


class OrderNotFound(Exception):
    pass


def set_order_status(order_id: int, status: str, engine: Engine | None = None) -> dict:
    """
    주문 상태를 PENDING/DELIVERED로 변경.
    - PENDING -> DELIVERED: process 1건 생성(기존 delivered 처리 로직 재사용)
    - DELIVERED -> PENDING: 상태만 되돌림
    """
    target = (status or "").strip().upper()
    if target not in ("PENDING", "DELIVERED"):
        raise ValueError("status must be PENDING or DELIVERED")

    if target == "DELIVERED":
        err, process_id = set_order_delivered_and_create_process(order_id, engine=engine)
        if err:
            raise ValueError(err)
        return {"order_id": order_id, "status": "DELIVERED", "process_id": process_id}

    with get_session() as session:
        order = session.get(Order, order_id)
        if not order:
            raise OrderNotFound()
        order.status = "PENDING"
        session.flush()
    return {"order_id": order_id, "status": "PENDING"}


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


def list_orders(engine: Engine | None = None) -> list[dict]:
    """전체 주문 목록 조회. 각 주문에 order_items 포함(품목명=브랜드+종류+용량). order_id 오름차순."""
    with get_session() as session:
        # item_code -> 물품명, 용량(1L/2L 등, 주문관리 1L·2L 컬럼 집계용)
        rows = session.execute(
            text("SELECT item_code, name, COALESCE(capacity, '') FROM products")
        ).fetchall()
        product_names = {row[0]: row[1] for row in rows} if rows else {}
        product_capacity = {row[0]: (row[2] or "").strip() for row in rows} if rows else {}

        orders_query = session.query(Order).order_by(Order.order_id.asc())
        result = []
        for order in orders_query:
            items = [
                {
                    "order_item_id": oi.order_item_id,
                    "item_code": oi.item_code or "",
                    "expected_qty": oi.expected_qty or 0,
                    "product_name": product_names.get(oi.item_code, oi.item_code or ""),
                    "capacity": product_capacity.get(oi.item_code, ""),
                }
                for oi in order.order_items
            ]
            result.append(
                {
                    "order_id": order.order_id,
                    "order_date": order.order_date.isoformat() if order.order_date else "",
                    "status": (order.status or "").strip().upper(),
                    "items": items,
                }
            )
        return result


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


def set_order_delivered_and_create_process(
    order_id: int, engine: Engine | None = None
) -> tuple[str | None, int | None]:
    """
    주문을 DELIVERED로 바꾸고 processes에 1건 추가. 한 트랜잭션으로 처리하며,
    process INSERT 실패 시 orders 변경도 롤백되어 PENDING 유지.

    트랜잭션 경계: 아래 with get_session() 블록 전체가 하나의 트랜잭션.
    - 블록 안의 order UPDATE와 process INSERT는 같은 session에서 실행됨.
    - 블록 정상 종료 시 get_session()이 commit() 한 번 호출 → 둘 다 반영.
    - 블록 안에서 예외 시 get_session()이 rollback() → 둘 다 취소.

    반환: (에러 메시지, process_id). 성공 시 (None, process_id), 실패 시 (에러문구, None).
    없으면 OrderNotFound.
    """
    with get_session() as session:
        order = session.get(Order, order_id)
        if not order:
            raise OrderNotFound()
        if (order.status or "").strip().upper() == "DELIVERED":
            return ("이미 입고한 주문입니다.", None)
        order.status = "DELIVERED"
        session.flush()
        process = Process(
            order_id=order_id,
            start_time=None,  # 공정 실제 시작 시 별도 설정 (orders가 설정하지 않음)
            end_time=None,
            status="NOT_STARTED",
        )
        session.add(process)
        session.flush()
        process_id = process.process_id
    logger.info("order_id=%s delivered, process_id=%s", order_id, process_id)
    return (None, process_id)
