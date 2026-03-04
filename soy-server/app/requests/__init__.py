"""
PC 브릿지 요청 핸들러: 액션별로 auth / orders / processes / workers 파일에서 처리.
인증 불필요: handle_no_auth. admin 필수: handle_admin_only.
"""
from typing import Any, Callable

Result = tuple[bool, Any, str]

from app.requests import auth as _auth
from app.requests import orders as _orders
from app.requests import processes as _processes
from app.requests import workers as _workers

import logging
logger = logging.getLogger(__name__)


def handle_no_auth(
    action: str,
    body: dict[str, Any],
    *,
    session_add: Callable[[str, int], None],
    session_remove: Callable[[str], None],
) -> Result | None:

    """인증 불필요 액션 처리. 처리한 경우 (ok, body, err) 반환, 아니면 None."""
    logger.info("인증 불필요 액션 처리. 처리한 경우 (ok, body, err) 반환, 아니면 None.")

    result = _auth.handle(action, body, session_add=session_add, session_remove=session_remove)
    if result is not None:
        return result
    result = _orders.handle(action, body)
    if result is not None:
        return result
    result = _processes.handle(action, body)
    if result is not None:
        return result
    result = _workers.handle(action, body)
    if result is not None:
        return result
    return None


def handle_admin_only(action: str, body: dict[str, Any]) -> Result:
    """admin 인증 후에만 호출. Worker CRUD 및 관리자 전용 조회 액션."""
    logger.info("admin 인증 후에만 호출. Worker CRUD 등.")
    res = _workers.handle(action, body)
    if res is not None:
        return res
    res = _processes.handle(action, body)
    if res is not None:
        return res
    return (False, None, f"Unknown admin action: {action}")


__all__ = ["Result", "handle_no_auth", "handle_admin_only"]
