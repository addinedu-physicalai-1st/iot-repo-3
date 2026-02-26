"""create inbounds, inbound_items (stock/outbounds 없음, inbound_items 로 통합)

요구사항 대응:
  1) QR로 물품 등록 → inbounds(1건) + inbound_items(상자 단위, 1행=1상자).
  2) 분류 여부 → inbound_items.status(미분류/분류완료/출고됨), classified_at, warehouse.
  3) 창고 현황 → inbound_items 에서 status='분류완료' 인 행을 product_id·warehouse 별로 COUNT.

Revision ID: 004
Revises: 003
Create Date: 2025-02-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET NAMES utf8mb4")
    op.execute("SET FOREIGN_KEY_CHECKS = 0")

    # 입고 건 (QR 스캔 1건). 요구 1) QR 등록 시 1 row (요구 2는 inbound_items에서 조회)
    op.execute("""
        CREATE TABLE IF NOT EXISTS `inbounds` (
            `inbound_id`                  INT UNSIGNED NOT NULL COMMENT '입고 id',
            `status`                      ENUM('등록됨', '분류중', '완료') NOT NULL DEFAULT '등록됨' COMMENT '분류 상태',
            `created_at`                  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `classification_completed_at` DATETIME    NULL COMMENT '분류 완료 시각',
            PRIMARY KEY (`inbound_id`),
            KEY `idx_inbounds_status` (`status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 입고 건별 상자 단위 (1행 = 1상자). 상태: 미분류 → 분류완료 → 출고됨. 창고 현황은 분류완료 행 집계로 조회
    op.execute("""
        CREATE TABLE IF NOT EXISTS `inbound_items` (
            `inbound_item_id`       INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '상자 고유 id',
            `inbound_id`            INT UNSIGNED NOT NULL COMMENT '입고 id',
            `product_id`            INT UNSIGNED NOT NULL COMMENT '물품',
            `status`                ENUM('미분류', '분류완료', '출고됨') NOT NULL DEFAULT '미분류' COMMENT '상태',
            `classified_at`         DATETIME    NULL COMMENT '분류 완료 시각',
            `warehouse`             ENUM('국내', '해외', '미분류') NULL COMMENT '분류 완료 시 들어간 창고',
            `outbound_at`           DATETIME    NULL COMMENT '출고 시각',
            PRIMARY KEY (`inbound_item_id`),
            CONSTRAINT `fk_inbound_items_inbound` FOREIGN KEY (`inbound_id`) REFERENCES `inbounds` (`inbound_id`) ON DELETE CASCADE,
            CONSTRAINT `fk_inbound_items_product` FOREIGN KEY (`product_id`) REFERENCES `products` (`product_id`) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    op.execute("SET FOREIGN_KEY_CHECKS = 1")


def downgrade() -> None:
    op.execute("SET FOREIGN_KEY_CHECKS = 0")
    op.execute("DROP TABLE IF EXISTS `inbound_items`")
    op.execute("DROP TABLE IF EXISTS `inbounds`")
    op.execute("SET FOREIGN_KEY_CHECKS = 1")
