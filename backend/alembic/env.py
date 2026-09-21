"""Alembic 运行环境。

连接串优先级：程序化覆盖（``run_migrations(db_url)``）> 应用配置
（``settings.database_url``，可由环境变量 ``DATABASE_URL`` 覆盖）。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings, sqlite_directory  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: E402,F401  确保模型注册到 metadata

config = context.config
url_override = config.attributes.get("url_override")
config.set_main_option("sqlalchemy.url", url_override or settings.database_url)

database_url = config.get_main_option("sqlalchemy.url")

# SQLite 不会自动创建父目录，命令行走 alembic 时也要先建好 data/ 之类的位置
database_dir = sqlite_directory(database_url)
if database_dir is not None:
    database_dir.mkdir(parents=True, exist_ok=True)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
