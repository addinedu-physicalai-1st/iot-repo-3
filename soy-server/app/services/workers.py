"""
Worker CRUD — DB 로직만. HTTP/TCP 핸들러에서 공통 사용.
ORM 사용.
"""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine

from app.database import get_session
from app.models import Admin, Worker,AccessLog

import logging
logger = logging.getLogger(__name__)

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

#-----------------------------------------------------------------#
# 작업일시 : 2026년 3월 3일 15:45
# 작업자 : 이준근
# 설명  : 작업자의 핵심 식별 정보(ID, 이름, 카드UID)만 반환합니다.
#-----------------------------------------------------------------#
def _to_worker_identity(w: Worker) -> dict:
    return {
        "worker_id": w.worker_id,
        "name": w.name,
        "card_uid": w.card_uid,
    }
#-----------------------------------------------------------------#


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

#-----------------------------------------------------------------#
# 작업일시 : 2026년 3월 3일 15:35
# 작업자 : 이준근
# 설명  : card_uid를 기반으로 작업자 정보를 조회합니다.
#-----------------------------------------------------------------#
def get_worker_by_card_uid(card_uid: str, engine: Engine | None = None) -> dict | None:
    card_uid = card_uid.strip()
    with get_session() as session:
        # card_uid가 일치하는 첫 번째 레코드를 조회
        worker = session.execute(
            select(Worker).where(Worker.card_uid == card_uid)
        ).scalars().first()
        
        # 결과가 없으면 None 반환
        if not worker:
            return None
            
        # 결과가 있으면 기존 변환 로직을 사용하여 dict 반환
        return _to_worker_identity(worker)
#-----------------------------------------------------------------#
    
#-----------------------------------------------------------------#
# 작업일시 : 2026년 3월 3일 20:15
# 작업자 : 이준근
# 설명  : AccessLog 객체를 생성하여 session.add()로 저장합니다.
#-----------------------------------------------------------------#
def create_access_log(worker_id: int, direction: str) -> bool:
    """
    worker_id와 direction(enter/exit)을 받아 출입 로그를 기록합니다.
    객체 생성 후 session.add()를 사용하여 인서트합니다.
    """
    from datetime import datetime
    
    # 1. direction 값 검증
    if direction not in ["enter", "exit"]:
        print(f"⚠️ 유효하지 않은 방향: {direction}")
        return False

    # 2. 세션 컨텍스트 시작
    with get_session() as session:
        try:
            # 3. AccessLog 인스턴스(객체) 생성
            new_log = AccessLog(
                worker_id=worker_id,
                direction=direction,
                checked_at=datetime.now()
            )
            logger.info(f"AccessLog 1: {worker_id})")
            
            # 4. 세션에 객체 추가 (INSERT 준비)
            session.add(new_log)

            logger.info(f"AccessLog 2: {worker_id})")
            
            # 5. (선택사항) 만약 저장 직후 생성된 access_log_id가 바로 필요하다면:
            # session.flush() 
            
            # with 블록 종료 시 database.py의 get_session에 의해 자동 commit() 됨
            return True
            
        except Exception as e:
            # 예외 발생 시 get_session에 의해 자동 rollback() 됨
            print(f"❌ 로그 저장 실패 (Worker: {worker_id}): {e}")
            return False
#-----------------------------------------------------------------#