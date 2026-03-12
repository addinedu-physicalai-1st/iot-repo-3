"""seed orders + order_items: 발주 3건, 총 수량 3/4/5개, 1L·2L 골고루

Revision ID: 007
Revises: 006
Create Date: 2025-02-26
"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 발주 3건: order_id·order_item_id 고정. items = (order_item_id, item_code, expected_qty)
# 총합 3/4/5개, 1L·2L 골고루
ORDERS_SEED = [
    {
        "order_id": 1,
        "order_date": datetime(2025, 2, 20, 10, 0, 0),
        "status": "PENDING",
        "items": [
            (1, "sampyo_jin_1l", 1),
            (2, "sampyo_guk_1l", 1),
            (3, "mongo_jin_2l", 1),
        ],
    },
    {
        "order_id": 2,
        "order_date": datetime(2025, 2, 22, 14, 0, 0),
        "status": "PENDING",
        "items": [
            (4, "mongo_jin_1l", 1),
            (5, "sampyo_guk_1l", 1),
            (6, "sampyo_jin_2l", 1),
            (7, "mongo_guk_2l", 1),
        ],
    },
    {
        "order_id": 3,
        "order_date": datetime(2025, 2, 24, 9, 0, 0),
        "status": "PENDING",
        "items": [
            (8, "sampyo_jin_1l", 1),
            (9, "mongo_guk_1l", 1),
            (10, "sampyo_guk_1l", 1),
            (11, "sampyo_jin_2l", 1),
            (12, "mongo_jin_2l", 1),
        ],
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for row in ORDERS_SEED:
        order_id = row["order_id"]
        conn.execute(
            text(
                "INSERT INTO `orders` (`order_id`, `order_date`, `status`) "
                "VALUES (:order_id, :order_date, :status)"
            ),
            {
                "order_id": order_id,
                "order_date": row["order_date"],
                "status": row["status"],
            },
        )
        for order_item_id, item_code, expected_qty in row["items"]:
            conn.execute(
                text(
                    "INSERT INTO `order_items` (`order_item_id`, `order_id`, `item_code`, `expected_qty`) "
                    "VALUES (:order_item_id, :order_id, :item_code, :expected_qty)"
                ),
                {
                    "order_item_id": order_item_id,
                    "order_id": order_id,
                    "item_code": item_code,
                    "expected_qty": expected_qty,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    # order_id 1, 2, 3 고정이므로 해당 행만 삭제 (order_items 먼저)
    conn.execute(
        text("DELETE FROM order_items WHERE order_id IN (1, 2, 3)")
    )
    conn.execute(
        text("DELETE FROM orders WHERE order_id IN (1, 2, 3)")
    )
