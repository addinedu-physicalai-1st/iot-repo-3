"""seed processes: 분류공정작업 시드 1건 (order_id=1, WAITING)

Revision ID: 013
Revises: 012
Create Date: 2025-03-01

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # order_id=1 은 007 시드 orders에 존재. processes 비어 있을 때만 공정 시드 1건 삽입
    conn.execute(
        text(
            """
            INSERT INTO `processes` (
                `order_id`, `start_time`, `end_time`, `status`,
                `total_qty`, `success_1l_qty`, `success_2l_qty`, `unclassified_qty`
            )
            SELECT 1, NULL, NULL, 'NOT_STARTED', 0, 0, 0, 0 FROM DUAL
            WHERE EXISTS (SELECT 1 FROM `orders` WHERE `order_id` = 1)
              AND (SELECT COUNT(*) FROM `processes`) = 0
        """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    # 시드 1건 제거 (order_id=1, WAITING, 수량 전부 0)
    conn.execute(
        text(
            """
            DELETE FROM `processes`
            WHERE `order_id` = 1 AND `status` = 'NOT_STARTED'
              AND `total_qty` = 0 AND `success_1l_qty` = 0
              AND `success_2l_qty` = 0 AND `unclassified_qty` = 0
            LIMIT 1
        """
        )
    )
