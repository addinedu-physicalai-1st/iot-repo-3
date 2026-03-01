"""admin password_hash NULL 허용 + admin·workers 시드 데이터

- admin.password_hash: NOT NULL → NULL (시드 admin은 비밀번호 없이 생성)
- admin 테이블이 비어 있으면 admin 1건 삽입 (password_hash=NULL)
- admin_id=1 존재 시 workers 시드 2건 삽입 (card_uid로 중복 방지)

Revision ID: 012
Revises: 011
Create Date: 2025-03-01

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WORKERS_SEED = [
    (1, "시드작업자1", "seed_worker_01"),
    (1, "시드작업자2", "seed_worker_02"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. admin.password_hash NULL 허용
    conn.execute(
        text(
            "ALTER TABLE `admin` MODIFY COLUMN `password_hash` VARCHAR(255) NULL"
        )
    )

    # 2. admin 테이블이 비어 있으면 첫 admin 1건 삽입 (비밀번호 없음)
    conn.execute(
        text("""
            INSERT INTO `admin` (`password_hash`, `created_at`, `updated_at`)
            SELECT NULL, NOW(), NOW() FROM DUAL
            WHERE (SELECT COUNT(*) FROM `admin`) = 0
        """)
    )

    # 3. admin_id=1이 있을 때만 workers 시드 삽입 (card_uid 중복 시 스킵)
    for admin_id, name, card_uid in WORKERS_SEED:
        conn.execute(
            text("""
                INSERT INTO `workers` (`admin_id`, `name`, `card_uid`, `created_at`)
                SELECT :admin_id, :name, :card_uid, NOW() FROM DUAL
                WHERE EXISTS (SELECT 1 FROM `admin` WHERE `admin_id` = :admin_id)
                  AND NOT EXISTS (SELECT 1 FROM `workers` WHERE `card_uid` = :card_uid)
            """),
            {"admin_id": admin_id, "name": name, "card_uid": card_uid},
        )


def downgrade() -> None:
    conn = op.get_bind()

    # 시드 workers 제거 (card_uid로 식별)
    conn.execute(
        text("DELETE FROM `workers` WHERE `card_uid` IN ('seed_worker_01', 'seed_worker_02')")
    )

    # 시드 admin 제거 (admin_id=1 이고 password_hash가 NULL인 경우만)
    conn.execute(
        text(
            "DELETE FROM `admin` WHERE `admin_id` = 1 AND `password_hash` IS NULL"
        )
    )

    # admin.password_hash 다시 NOT NULL
    conn.execute(
        text(
            "ALTER TABLE `admin` MODIFY COLUMN `password_hash` VARCHAR(255) NOT NULL"
        )
    )
