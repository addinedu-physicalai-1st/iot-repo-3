"""창고 재고(inventory) 조회."""

from sqlalchemy import text

from app.database import get_session
from app.models import Inventory


def list_inventory_status_stats() -> list[dict]:
    """
    재고 현황 통계: brand × category × inventory_id 별 건수.
    item_sorting_logs + products 조인, is_error=0, inventory_id IN (1,2,3).
    반환: [{"brand": "몽고", "category": "진간장", "inventory_id": 1, "count": 42}, ...]
    """
    with get_session() as session:
        stmt = text("""
            SELECT p.brand, p.category, l.inventory_id, COUNT(*) AS cnt
            FROM item_sorting_logs l
            JOIN products p ON l.item_code = p.item_code
            WHERE l.is_error = 0 AND l.inventory_id IN (1, 2, 3)
            GROUP BY p.brand, p.category, l.inventory_id
            ORDER BY p.brand, p.category, l.inventory_id
        """)
        rows = session.execute(stmt).fetchall()
        return [
            {
                "brand": row[0] or "",
                "category": row[1] or "",
                "inventory_id": row[2],
                "count": int(row[3]),
            }
            for row in rows
        ]


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
