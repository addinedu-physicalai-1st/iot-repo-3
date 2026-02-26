"""
DB 연결. 환경변수 SOY_DATABASE_URL 또는 MYSQL_* 사용 (alembic/env와 동일).
Engine + ORM Session 제공.
"""
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

_env = os.environ


def _get_url() -> str:
    url = _env.get("SOY_DATABASE_URL")
    if url:
        return url
    user = _env.get("MYSQL_USER", "soy")
    password = _env.get("MYSQL_PASSWORD", "soy")
    host = _env.get("MYSQL_HOST", "127.0.0.1")
    port = _env.get("MYSQL_PORT", "3333")
    database = _env.get("MYSQL_DATABASE", "soydb")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_get_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """ORM 세션 컨텍스트. yield 후 commit(정상) 또는 rollback(예외)."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
