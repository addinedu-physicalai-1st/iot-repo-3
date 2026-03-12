"""PC 브릿지: 주문 조회·입고 (작업자 화면 주문 관리, 인증 불필요)."""
import logging
from typing import Any

from app.services import orders as orders_module

Result = tuple[bool, Any, str]
logger = logging.getLogger(__name__)


def handle(action: str, body: dict[str, Any]) -> Result | None:
    """list_orders, get_order, get_order_id_by_order_item_id, order_mark_delivered, order_set_status."""
    if action == "list_orders":
        orders_list = orders_module.list_orders()
        return (True, orders_list, "")
    if action == "get_order":
        oid = body.get("order_id")
        if oid is None:
            return (False, None, "order_id required")
        order = orders_module.get_order(int(oid))
        if order is None:
            return (False, None, "주문을 찾을 수 없습니다.")
        return (True, order, "")
    if action == "get_order_id_by_order_item_id":
        oiid = body.get("order_item_id")
        if oiid is None:
            return (False, None, "order_item_id required")
        oid = orders_module.get_order_id_by_order_item_id(int(oiid))
        if oid is None:
            return (False, None, "주문 상세를 찾을 수 없습니다.")
        return (True, {"order_id": oid}, "")
    if action == "order_mark_delivered":
        oid = body.get("order_id")
        oiid = body.get("order_item_id")
        if oid is None and oiid is None:
            return (False, None, "order_id 또는 order_item_id가 필요합니다.")
        if oid is None:
            oid = orders_module.get_order_id_by_order_item_id(int(oiid))
            if oid is None:
                return (False, None, "주문 상세를 찾을 수 없습니다.")
        else:
            oid = int(oid)
        try:
            err, process_id = orders_module.set_order_delivered_and_create_process(oid)
        except orders_module.OrderNotFound:
            return (False, None, "주문을 찾을 수 없습니다.")
        except Exception as e:
            logger.warning("order_mark_delivered: 트랜잭션 실패 order_id=%s: %s", oid, e)
            return (False, None, f"입고 등록 실패. 주문은 변경되지 않았습니다. ({e})")
        if err:
            return (False, None, err)
        return (True, {"order_id": oid, "process_id": process_id}, "")
    if action == "order_set_status":
        oid = body.get("order_id")
        status = body.get("status")
        if oid is None:
            return (False, None, "order_id required")
        if status is None:
            return (False, None, "status required")
        try:
            out = orders_module.set_order_status(int(oid), str(status))
            return (True, out, "")
        except orders_module.OrderNotFound:
            return (False, None, "주문을 찾을 수 없습니다.")
        except ValueError as e:
            return (False, None, str(e))
        except Exception as e:
            logger.warning("order_set_status 실패 order_id=%s status=%s: %s", oid, status, e)
            return (False, None, f"주문 상태 변경 실패: {e}")
    return None
