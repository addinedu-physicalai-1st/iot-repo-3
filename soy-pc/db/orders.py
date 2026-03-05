"""orders 상태 변경 로컬 DB fallback."""

from db.connection import get_connection


def set_order_status_pending(order_id: int) -> None:
    """주문 상태를 PENDING으로 변경. 없으면 RuntimeError."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                ("PENDING", int(order_id)),
            )
            if cur.rowcount <= 0:
                raise RuntimeError("주문을 찾을 수 없습니다.")
