"""inbound 테이블 제거, processes를 order_id FK로 직접 연결

- item_sorting_logs: inbound_id 컬럼·FK·인덱스 제거
- processes: inbound_id 제거, order_id FK 추가 (기존 데이터는 inbounds에서 복사 후 제거)
- inbounds 테이블 삭제

Revision ID: 009
Revises: 008
Create Date: 2025-02-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) item_sorting_logs: inbound_id 제거
    op.drop_constraint(
        "fk_item_sorting_logs_inbound",
        "item_sorting_logs",
        type_="foreignkey",
    )
    op.drop_index("idx_item_sorting_logs_inbound_id", table_name="item_sorting_logs")
    op.drop_column("item_sorting_logs", "inbound_id")

    # 2) processes: order_id 추가 후 기존 데이터 이전
    op.execute(
        "ALTER TABLE `processes` ADD COLUMN `order_id` INT UNSIGNED NULL COMMENT '발주 ID' AFTER `process_id`"
    )
    op.execute("""
        UPDATE `processes` p
        INNER JOIN `inbounds` i ON p.inbound_id = i.inbound_id
        SET p.order_id = i.order_id
    """)
    op.execute(
        "ALTER TABLE `processes` MODIFY COLUMN `order_id` INT UNSIGNED NOT NULL COMMENT '발주 ID'"
    )
    op.create_foreign_key(
        "fk_processes_order",
        "processes",
        "orders",
        ["order_id"],
        ["order_id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.create_index("idx_processes_order_id", "processes", ["order_id"])

    op.drop_constraint("fk_processes_inbound", "processes", type_="foreignkey")
    op.drop_index("idx_processes_inbound_id", table_name="processes")
    op.drop_column("processes", "inbound_id")

    # 3) inbounds 테이블 삭제
    op.execute("DROP TABLE IF EXISTS `inbounds`")


def downgrade() -> None:
    op.execute("SET FOREIGN_KEY_CHECKS = 0")

    # inbounds 재생성 (008 이전 스키마: status 없음 → 005 기준으로 inbound_id, order_id, inbound_date만)
    op.execute("""
        CREATE TABLE `inbounds` (
            `inbound_id`   VARCHAR(50)  NOT NULL COMMENT '입고번호',
            `order_id`     INT UNSIGNED NOT NULL COMMENT '발주 ID',
            `inbound_date` DATETIME     NOT NULL COMMENT '입고 일시',
            PRIMARY KEY (`inbound_id`),
            KEY `idx_inbounds_order_id` (`order_id`),
            CONSTRAINT `fk_inbounds_order` FOREIGN KEY (`order_id`) REFERENCES `orders` (`order_id`) ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # processes에 inbound_id 복원 (order_id→inbound_id 매핑 복원 불가, 데이터 손실)
    op.execute(
        "ALTER TABLE `processes` ADD COLUMN `inbound_id` VARCHAR(50) NULL COMMENT '입고번호' AFTER `process_id`"
    )
    # downgrade 시 order_id→inbound_id 매핑 복원 불가(데이터 손실). FK만 복원
    op.drop_constraint("fk_processes_order", "processes", type_="foreignkey")
    op.drop_index("idx_processes_order_id", table_name="processes")
    op.drop_column("processes", "order_id")
    op.create_index("idx_processes_inbound_id", "processes", ["inbound_id"])
    op.create_foreign_key(
        "fk_processes_inbound",
        "processes",
        "inbounds",
        ["inbound_id"],
        ["inbound_id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )

    # item_sorting_logs에 inbound_id 복원 (NULL 허용)
    op.execute(
        "ALTER TABLE `item_sorting_logs` ADD COLUMN `inbound_id` VARCHAR(50) NULL COMMENT '입고번호' AFTER `process_id`"
    )
    op.create_index("idx_item_sorting_logs_inbound_id", "item_sorting_logs", ["inbound_id"])
    op.create_foreign_key(
        "fk_item_sorting_logs_inbound",
        "item_sorting_logs",
        "inbounds",
        ["inbound_id"],
        ["inbound_id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )

    op.execute("SET FOREIGN_KEY_CHECKS = 1")
