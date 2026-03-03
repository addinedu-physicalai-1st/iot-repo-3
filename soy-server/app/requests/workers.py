"""PC 브릿지: Worker CRUD + 출입 로그 조회 (admin 로그인 필수, 호출 전 _require_admin 필요)."""
from typing import Any

from app.services import access_logs as access_logs_module
from app.services import workers as workers_module

Result = tuple[bool, Any, str]


def handle(action: str, body: dict[str, Any]) -> Result:
    """get_first_admin_id, list_workers, create_worker, update_worker, delete_worker, list_access_logs."""
    if action == "list_access_logs":
        limit = body.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 500
        else:
            limit = 500
        worker_name = body.get("worker_name")
        if worker_name is not None and not isinstance(worker_name, str):
            worker_name = None
        return (
            True,
            access_logs_module.list_access_logs(limit=limit, worker_name=worker_name),
            "",
        )
    if action == "get_first_admin_id":
        aid = workers_module.get_first_admin_id()
        return (True, {"admin_id": aid} if aid is not None else None, "")
    if action == "list_workers":
        return (True, workers_module.list_workers(), "")
    if action == "create_worker":
        aid = body.get("admin_id")
        name = body.get("name", "")
        uid = body.get("card_uid", "")
        if aid is None:
            return (False, None, "admin_id required")
        out = workers_module.create_worker(int(aid), name, uid)
        return (True, out, "")
    if action == "update_worker":
        wid = body.get("worker_id")
        if wid is None:
            return (False, None, "worker_id required")
        out = workers_module.update_worker(
            int(wid),
            name=body.get("name"),
            card_uid=body.get("card_uid"),
        )
        return (True, out, "")
    if action == "delete_worker":
        wid = body.get("worker_id")
        if wid is None:
            return (False, None, "worker_id required")
        workers_module.delete_worker(int(wid))
        return (True, None, "")
    return (False, None, f"Unknown action: {action}")
