"""inventory 테이블 조회 (soy_db 직접 연결)."""
from db.connection import get_connection


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
