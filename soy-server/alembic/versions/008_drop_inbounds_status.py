"""drop inbounds.status: 인바운드에는 상태 없음

Revision ID: 008
Revises: 007
Create Date: 2025-02-27

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import Column, String

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_inbounds_status", table_name="inbounds")
    op.drop_column("inbounds", "status")


def downgrade() -> None:
    op.add_column(
        "inbounds",
        Column("status", String(20), nullable=False, server_default="WAITING"),
    )
    op.create_index("idx_inbounds_status", "inbounds", ["status"])
