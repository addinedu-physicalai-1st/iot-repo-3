"""
관리자 비밀번호 검증·최초 등록. DB의 admin 테이블 사용.
ORM 사용.
"""
import bcrypt
from sqlalchemy import select

from app.database import get_session
from app.models import Admin

BCRYPT_MAX_BYTES = 72


def _password_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:BCRYPT_MAX_BYTES]


def set_first_admin_password(plain_password: str) -> None:
    """첫 번째 admin row에 비밀번호가 없으면 설정. 이미 있으면 ValueError."""
    hashed = bcrypt.hashpw(
        _password_bytes(plain_password.strip()),
        bcrypt.gensalt(),
    ).decode("ascii")
    with get_session() as session:
        admin = session.execute(
            select(Admin).order_by(Admin.admin_id).limit(1)
        ).scalars().first()
        if not admin:
            raise ValueError("등록된 관리자가 없습니다.")
        if admin.password_hash and admin.password_hash.strip():
            raise ValueError("이미 관리자 비밀번호가 설정되어 있습니다.")
        admin.password_hash = hashed
        session.flush()


def first_admin_needs_password() -> bool:
    """첫 번째 admin row가 있고 비밀번호가 없으면 True (초기 설정 필요)."""
    with get_session() as session:
        admin = session.execute(
            select(Admin).order_by(Admin.admin_id).limit(1)
        ).scalars().first()
        if not admin:
            return False
        stored = admin.password_hash
        return not (stored and stored.strip())


def verify_admin_password(plain: str) -> bool:
    """DB 첫 번째 admin의 password_hash와 일치하면 True."""
    with get_session() as session:
        admin = session.execute(
            select(Admin).order_by(Admin.admin_id).limit(1)
        ).scalars().first()
        if not admin:
            return False
        stored = admin.password_hash
    if not stored:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(plain), stored.encode("ascii"))
    except Exception:
        return False
