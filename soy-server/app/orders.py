"""
주문(orders) 조회·상태 변경. 입고 시 pending → delivered.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import get_engine


class OrderNotFound(Exception):
    pass


def get_order(order_id: int, engine: Engine | None = None) -> dict | None:
    """order_id로 주문 조회. 없으면 None."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        row = conn.execute(
            text(
                "SELECT order_id, order_date, status FROM orders WHERE order_id = :oid"
            ),
            {"oid": order_id},
        ).fetchone()
        if not row:
            return None
        return {
            "order_id": row[0],
            "order_date": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "status": (row[2] or "").strip().upper(),
        }


def get_order_id_by_order_item_id(order_item_id: int, engine: Engine | None = None) -> int | None:
    """order_item_id로 order_id 조회. 없으면 None."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT order_id FROM order_items WHERE order_item_id = :oiid"),
            {"oiid": order_item_id},
        ).fetchone()
        return int(row[0]) if row else None


def set_order_delivered(order_id: int, engine: Engine | None = None) -> str | None:
    """
    주문 상태를 DELIVERED로 변경.
    이미 DELIVERED면 None 반환(에러 메시지용).
    없으면 OrderNotFound.
    성공 시 None(에러 없음).
    """
    eng = engine or get_engine()
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM orders WHERE order_id = :oid"),
            {"oid": order_id},
        ).fetchone()
        if not row:
            raise OrderNotFound()
        status = (row[0] or "").strip().upper()
        if status == "DELIVERED":
            return "이미 입고한 주문입니다."
        conn.execute(
            text("UPDATE orders SET status = 'DELIVERED' WHERE order_id = :oid"),
            {"oid": order_id},
        )
        conn.commit()
    return None
