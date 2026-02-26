"""
Worker CRUD — DB 로직만. HTTP/TCP 핸들러에서 공통 사용.
ORM 사용.
"""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine

from app.database import get_session
from app.models import Admin, Worker


class WorkerNotFound(Exception):
    pass


class WorkerCreateConflict(Exception):
    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(detail)


def _row_to_worker(w: Worker) -> dict:
    return {
        "worker_id": w.worker_id,
        "admin_id": w.admin_id,
        "name": w.name,
        "card_uid": w.card_uid,
        "created_at": w.created_at.isoformat() if w.created_at else str(w.created_at),
    }


def count_admins(engine: Engine | None = None) -> int:
    """admin 테이블 레코드 수."""
    with get_session() as session:
        return session.scalar(select(func.count()).select_from(Admin)) or 0


def get_first_admin_id(engine: Engine | None = None) -> int | None:
    with get_session() as session:
        admin = session.execute(
            select(Admin.admin_id).order_by(Admin.admin_id).limit(1)
        ).scalars().first()
        return int(admin) if admin is not None else None


def list_workers(engine: Engine | None = None) -> list[dict]:
    with get_session() as session:
        workers = session.execute(
            select(Worker).order_by(Worker.worker_id)
        ).scalars().all()
        return [_row_to_worker(w) for w in workers]


def create_worker(
    admin_id: int,
    name: str,
    card_uid: str,
    engine: Engine | None = None,
) -> dict:
    name = name.strip()
    card_uid = card_uid.strip()
    with get_session() as session:
        worker = Worker(admin_id=admin_id, name=name, card_uid=card_uid)
        session.add(worker)
        try:
            session.flush()
        except IntegrityError as e:
            orig = getattr(e, "orig", e)
            if "Duplicate" in str(orig) or "card_uid" in str(orig):
                raise WorkerCreateConflict("이 카드 UID는 이미 등록된 작업자가 있습니다.") from e
            raise
        session.refresh(worker)
        return _row_to_worker(worker)


def update_worker(
    worker_id: int,
    *,
    name: str | None = None,
    card_uid: str | None = None,
    engine: Engine | None = None,
) -> dict:
    with get_session() as session:
        worker = session.get(Worker, worker_id)
        if not worker:
            raise WorkerNotFound()
        if name is not None:
            worker.name = name.strip()
        if card_uid is not None:
            worker.card_uid = card_uid.strip()
        try:
            session.flush()
        except IntegrityError as e:
            orig = getattr(e, "orig", e)
            if "Duplicate" in str(orig) or "card_uid" in str(orig):
                raise WorkerCreateConflict(
                    "이 카드 UID는 이미 다른 작업자가 사용 중입니다."
                ) from e
            raise
        session.refresh(worker)
        return _row_to_worker(worker)


def delete_worker(worker_id: int, engine: Engine | None = None) -> None:
    with get_session() as session:
        worker = session.get(Worker, worker_id)
        if not worker:
            raise WorkerNotFound()
        session.delete(worker)
