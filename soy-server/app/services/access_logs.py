"""출입 로그 조회 — access_logs + workers join."""
from sqlalchemy import select
from sqlalchemy.engine import Engine

from app.database import get_session
from app.models import AccessLog, Worker


def list_access_logs(
    engine: Engine | None = None,
    limit: int = 500,
    worker_name: str | None = None,
) -> list[dict]:
    """출입 로그 목록 (최신순). worker name 포함. worker_name이 있으면 이름 부분 일치 필터."""
    with get_session() as session:
        stmt = (
            select(AccessLog, Worker.name)
            .join(Worker, AccessLog.worker_id == Worker.worker_id)
            .order_by(AccessLog.checked_at.desc())
            .limit(max(1, min(limit, 2000)))
        )
        search = (worker_name or "").strip()
        if search:
            stmt = stmt.where(Worker.name.contains(search, autoescape=True))
        rows = session.execute(stmt).all()
        return [
            {
                "access_log_id": log.access_log_id,
                "worker_id": log.worker_id,
                "worker_name": name or "",
                "checked_at": log.checked_at.isoformat() if log.checked_at else "",
                "direction": log.direction or "",
            }
            for log, name in rows
        ]
