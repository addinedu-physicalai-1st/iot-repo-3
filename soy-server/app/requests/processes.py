"""PC 브릿지: 공정 목록·시작·중지·수량 갱신 (작업자 화면 분류하기, 인증 불필요)."""
from typing import Any

from app.services import processes as processes_module

Result = tuple[bool, Any, str]


def handle(action: str, body: dict[str, Any]) -> Result | None:
    """list_processes, process_start, process_stop, process_update."""
    if action == "list_processes":
        lst = processes_module.list_processes()
        return (True, lst, "")
    if action == "process_start":
        pid = body.get("process_id")
        if pid is None:
            return (False, None, "process_id required")
        try:
            out = processes_module.start_process(int(pid))
            return (True, out, "")
        except processes_module.ProcessNotFound:
            return (False, None, "공정을 찾을 수 없습니다.")
    if action == "process_stop":
        pid = body.get("process_id")
        if pid is None:
            return (False, None, "process_id required")
        try:
            out = processes_module.stop_process(int(pid))
            return (True, out, "")
        except processes_module.ProcessNotFound:
            return (False, None, "공정을 찾을 수 없습니다.")
    if action == "process_update":
        pid = body.get("process_id")
        if pid is None:
            return (False, None, "process_id required")
        try:
            out = processes_module.update_process(
                int(pid),
                success_1l_qty=body.get("success_1l_qty"),
                success_2l_qty=body.get("success_2l_qty"),
                unclassified_qty=body.get("unclassified_qty"),
            )
            return (True, out, "")
        except processes_module.ProcessNotFound:
            return (False, None, "공정을 찾을 수 없습니다.")
    return None
