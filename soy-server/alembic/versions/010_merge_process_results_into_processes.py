"""process_results 제거, processes에 결과 컬럼 추가

- processes: total_qty, success_1l_qty, success_2l_qty, unclassified_qty 추가 (NOT NULL DEFAULT 0)
- process_results 테이블 삭제

Revision ID: 010
Revises: 009
Create Date: 2025-02-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE `processes`
        ADD COLUMN `total_qty`       INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '총 처리 수량',
        ADD COLUMN `success_1l_qty`  INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '1L 정상 분류 수량',
        ADD COLUMN `success_2l_qty`  INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '2L 정상 분류 수량',
        ADD COLUMN `unclassified_qty` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '미분류 수량'
    """)
    op.execute("DROP TABLE IF EXISTS `process_results`")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE `process_results` (
            `result_id`        INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '결과 로그 ID',
            `process_id`       INT UNSIGNED NOT NULL COMMENT '공정 작업 ID',
            `total_qty`        INT UNSIGNED NOT NULL COMMENT '총 처리 수량',
            `success_1l_qty`   INT UNSIGNED NOT NULL COMMENT '1L 정상 분류 수량',
            `success_2l_qty`   INT UNSIGNED NOT NULL COMMENT '2L 정상 분류 수량',
            `unclassified_qty` INT UNSIGNED NOT NULL COMMENT '미분류 수량',
            `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`result_id`),
            UNIQUE KEY `uk_process_results_process_id` (`process_id`),
            CONSTRAINT `fk_process_results_process` FOREIGN KEY (`process_id`) REFERENCES `processes` (`process_id`) ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    op.execute("""
        INSERT INTO `process_results` (process_id, total_qty, success_1l_qty, success_2l_qty, unclassified_qty, created_at)
        SELECT process_id, total_qty, success_1l_qty, success_2l_qty, unclassified_qty, NOW()
        FROM `processes`
    """)
    op.execute("""
        ALTER TABLE `processes`
        DROP COLUMN `total_qty`,
        DROP COLUMN `success_1l_qty`,
        DROP COLUMN `success_2l_qty`,
        DROP COLUMN `unclassified_qty`
    """)

