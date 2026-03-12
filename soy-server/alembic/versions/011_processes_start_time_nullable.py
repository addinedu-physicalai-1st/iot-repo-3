"""processes.start_time NULL 허용: orders 생성 시 미설정, 공정 시작 시 설정

Revision ID: 011
Revises: 010
Create Date: 2025-02-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `processes` MODIFY COLUMN `start_time` DATETIME NULL COMMENT '공정 시작 일시 (공정 시작 시 설정)'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `processes` MODIFY COLUMN `start_time` DATETIME NOT NULL COMMENT '공정 시작 일시'"
    )
