"""inventory 테이블 조회 (soy_db 직접 연결)."""
from db.connection import get_connection


def list_inventory_status_stats() -> list[dict]:
    """재고 현황: brand × category × inventory_id 별 건수. API 실패 시 fallback."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.brand, p.category, l.inventory_id, COUNT(*) AS cnt
                    FROM item_sorting_logs l
                    JOIN products p ON l.item_code = p.item_code
                    WHERE l.is_error = 0 AND l.inventory_id IN (1, 2, 3)
                    GROUP BY p.brand, p.category, l.inventory_id
                    ORDER BY p.brand, p.category, l.inventory_id
                """)
                rows = cur.fetchall()
                return [
                    {"brand": row[0] or "", "category": row[1] or "", "inventory_id": row[2], "count": row[3]}
                    for row in rows
                ]
    except Exception:
        return []


def list_inventory() -> list[dict]:
    """창고 재고 목록. inventory_id 순. API와 동일한 형태 반환."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT inventory_id, inventory_name, current_qty, updated_at "
                    "FROM inventory ORDER BY inventory_id"
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    inv_id, name, qty, updated = row
                    result.append({
                        "inventory_id": inv_id,
                        "inventory_name": name or "",
                        "current_qty": qty or 0,
                        "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else str(updated) if updated else None,
                    })
                return result
    except Exception:
        return []
