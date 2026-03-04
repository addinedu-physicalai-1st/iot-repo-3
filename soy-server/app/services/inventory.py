"""창고 재고(inventory) 조회."""

from app.database import get_session
from app.models import Inventory


def list_inventory() -> list[dict]:
    """inventory_id 순으로 창고 목록 반환."""
    with get_session() as session:
        rows = session.query(Inventory).order_by(Inventory.inventory_id).all()
        return [
            {
                "inventory_id": r.inventory_id,
                "inventory_name": r.inventory_name,
                "current_qty": r.current_qty,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
