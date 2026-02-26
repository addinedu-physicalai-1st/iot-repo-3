"""create products table and seed data

Revision ID: 003
Revises: 002
Create Date: 2025-02-26

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 배송지: 영문 제품명이면 해외, 아니면 국내 (ENUM: 국내, 해외)
OVERSEAS_NAMES = {"Soy sauce", "Dark soy sauce"}

PRODUCT_NAMES = [
    "국간장",
    "진간장",
    "Soy sauce",
    "Dark soy sauce",
]
BRANDS = ["샘표", "청정원"]


def _seed_rows():
    for name in PRODUCT_NAMES:
        destination = "해외" if name in OVERSEAS_NAMES else "국내"
        for brand in BRANDS:
            yield (name, brand, destination)


def upgrade() -> None:
    op.execute("SET NAMES utf8mb4")
    op.execute("SET FOREIGN_KEY_CHECKS = 0")

    op.execute("""
        CREATE TABLE IF NOT EXISTS `products` (
            `product_id`           INT UNSIGNED NOT NULL AUTO_INCREMENT,
            `product_name`         VARCHAR(100) NOT NULL COMMENT '물품명',
            `brand`                VARCHAR(50)  NOT NULL COMMENT '브랜드',
            `shipping_destination` ENUM('국내', '해외') NOT NULL COMMENT '배송지',
            PRIMARY KEY (`product_id`),
            KEY `idx_products_brand` (`brand`),
            KEY `idx_products_shipping_destination` (`shipping_destination`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    conn = op.get_bind()
    for name, brand, destination in _seed_rows():
        conn.execute(
            text(
                "INSERT INTO `products` (`product_name`, `brand`, `shipping_destination`) "
                "VALUES (:product_name, :brand, :shipping_destination)"
            ),
            {"product_name": name, "brand": brand, "shipping_destination": destination},
        )

    op.execute("SET FOREIGN_KEY_CHECKS = 1")


def downgrade() -> None:
    op.execute("SET FOREIGN_KEY_CHECKS = 0")
    op.execute("DROP TABLE IF EXISTS `products`")
    op.execute("SET FOREIGN_KEY_CHECKS = 1")
