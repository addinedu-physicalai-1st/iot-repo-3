"""TCP 응답 포맷 (PC 브릿지). Controller의 (ok, body, err) → 클라이언트로 보낼 JSON 구조."""
from typing import Any


def format_response(
    req_id: Any,
    ok: bool,
    body: Any,
    error: str | None,
) -> dict[str, Any]:
    """요청 id와 Controller 결과를 TCP 응답 dict로 만든다. 직렬화/전송은 호출부에서."""
    return {
        "type": "response",
        "id": req_id,
        "ok": ok,
        "body": body,
        "error": error if not ok else None,
    }
