"""
Alembic env — DB URL은 환경변수 사용.
  SOY_DATABASE_URL 또는 MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
ORM Base.metadata 연결로 향후 autogenerate 시 참조.
"""
import os
from logging.config import fileConfig

from sqlalchemy import create_engine
from alembic import context

from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    url = os.getenv("SOY_DATABASE_URL")
    if url:
        return url
    user = os.getenv("MYSQL_USER", "soy")
    password = os.getenv("MYSQL_PASSWORD", "soy")
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3333")
    database = os.getenv("MYSQL_DATABASE", "soydb")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
