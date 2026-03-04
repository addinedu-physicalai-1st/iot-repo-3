"""PC 브릿지: 재고 리포트 (admin 로그인 필수)."""

from typing import Any

from app.services import inventory as inventory_module

Result = tuple[bool, Any, str]


def handle(action: str, body: dict[str, Any]) -> Result | None:
    """list_inventory."""
    if action == "list_inventory":
        return (True, inventory_module.list_inventory(), "")
    return None
