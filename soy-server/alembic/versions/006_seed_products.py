"""seed products: 브랜드(샘표, 몽고) × 종류(진간장, 국간장) × 용량(1L, 2L). 물품명 = 브랜드 + 종류 + 용량

Revision ID: 006
Revises: 005
Create Date: 2025-02-26
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BRANDS = ("샘표", "몽고")
CATEGORIES = ("진간장", "국간장")
CAPACITIES = ("1L", "2L")


def _iter_seed_rows():
    for brand in BRANDS:
        for category in CATEGORIES:
            for capacity in CAPACITIES:
                # 물품명 = 브랜드 + 종류 + 용량
                name = f"{brand} {category} {capacity}"
                # item_code: 소문자 영문 조합 (QR/API용)
                code_slug = {
                    "샘표": "sampyo",
                    "몽고": "mongo",
                    "진간장": "jin",
                    "국간장": "guk",
                }
                item_code = f"{code_slug[brand]}_{code_slug[category]}_{capacity.lower()}"
                yield (item_code, name, brand, category, capacity)


def upgrade() -> None:
    conn = op.get_bind()
    for item_code, name, brand, category, capacity in _iter_seed_rows():
        conn.execute(
            text(
                "INSERT INTO `products` (`item_code`, `name`, `brand`, `category`, `capacity`) "
                "VALUES (:item_code, :name, :brand, :category, :capacity)"
            ),
            {
                "item_code": item_code,
                "name": name,
                "brand": brand,
                "category": category,
                "capacity": capacity,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    for item_code, *_ in _iter_seed_rows():
        conn.execute(text("DELETE FROM `products` WHERE `item_code` = :code"), {"code": item_code})
