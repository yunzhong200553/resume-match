"""数据库引擎与会话。"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db import models  # noqa: F401  注册所有模型

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite 默认关闭外键约束，这里统一打开，保证级联行为可预期。"""

    module = type(dbapi_connection).__module__ or ""
    if "sqlite" not in module:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话。"""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_all(engine_to_use: Engine | None = None) -> None:
    """建表（仅用于测试夹具，正式环境使用 Alembic 迁移）。"""

    Base.metadata.create_all(bind=engine_to_use or engine)
