"""
관리자 비밀번호 검증·최초 등록. DB의 admin 테이블 사용.
ORM 사용.
"""
import bcrypt
from sqlalchemy import func, select

from app.database import get_session
from app.models import Admin

BCRYPT_MAX_BYTES = 72


def _password_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:BCRYPT_MAX_BYTES]


def create_first_admin(plain_password: str) -> None:
    """admin 테이블이 비어 있을 때만 첫 관리자 등록. 이미 있으면 ValueError."""
    hashed = bcrypt.hashpw(
        _password_bytes(plain_password.strip()),
        bcrypt.gensalt(),
    ).decode("ascii")
    with get_session() as session:
        count = session.scalar(select(func.count()).select_from(Admin)) or 0
        if count > 0:
            raise ValueError("이미 관리자가 등록되어 있습니다.")
        session.add(Admin(password_hash=hashed))


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
