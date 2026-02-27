"""PC 브릿지: admin 로그인/로그아웃/관리자 수/최초 등록 (인증 불필요)."""
import uuid
from typing import Any, Callable

from app.services import workers
from app.auth import create_first_admin, verify_admin_password

Result = tuple[bool, Any, str]


def handle(
    action: str,
    body: dict[str, Any],
    *,
    session_add: Callable[[str, int], None],
    session_remove: Callable[[str], None],
) -> Result | None:
    """admin_login, admin_logout, admin_count, register_first_admin."""
    if action == "admin_login":
        password = (body.get("password") or "").strip()
        if not password:
            return (False, None, "Password required")
        if not verify_admin_password(password):
            return (False, None, "비밀번호가 올바르지 않습니다.")
        aid = workers.get_first_admin_id()
        if aid is None:
            return (False, None, "No admin registered")
        token = str(uuid.uuid4())
        session_add(token, aid)
        return (True, {"token": token, "admin_id": aid}, "")
    if action == "admin_logout":
        token = body.get("auth_token")
        if token:
            session_remove(str(token))
        return (True, None, "")
    if action == "admin_count":
        n = workers.count_admins()
        return (True, {"count": n}, "")
    if action == "register_first_admin":
        password = (body.get("password") or "").strip()
        if not password:
            return (False, None, "비밀번호를 입력하세요.")
        if len(password) < 4:
            return (False, None, "비밀번호는 4자 이상으로 설정하세요.")
        try:
            create_first_admin(password)
            return (True, None, "")
        except ValueError as e:
            return (False, None, str(e))
    return None
