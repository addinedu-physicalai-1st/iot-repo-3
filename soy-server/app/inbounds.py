"""
입고(inbounds) 등록. 주문 배송 도착 시 order_id 기준으로 1건 추가.
ORM 사용. (주문 delivered + inbound 생성은 orders.set_order_delivered_and_create_inbound 사용)
"""
from datetime import datetime
from sqlalchemy.engine import Engine

from app.database import get_session
from app.models import Inbound


def create_inbound_for_order(order_id: int, engine: Engine | None = None) -> str:
    """
    order_id에 대한 입고 1건을 inbounds에 추가.
    inbound_id = IN-{order_id}-{YYYYMMDDHHmmss}, status = WAITING.
    반환: 생성된 inbound_id.
    """
    now = datetime.utcnow()
    inbound_id = f"IN-{order_id}-{now.strftime('%Y%m%d%H%M%S')}"
    with get_session() as session:
        session.add(
            Inbound(
                inbound_id=inbound_id,
                order_id=order_id,
                inbound_date=now,
                status="WAITING",
            )
        )
    return inbound_id
