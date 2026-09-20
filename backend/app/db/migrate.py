"""以编程方式执行 Alembic 迁移。

应用启动时（``AUTO_MIGRATE=true``）调用，保证表结构与迁移脚本单一来源，
不用 ``Base.metadata.create_all`` 绕过迁移。
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from app.core.config import BACKEND_DIR, settings


def build_alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    url = database_url or settings.database_url
    config.set_main_option("sqlalchemy.url", url)
    # 用 attributes 明确标记程序化覆盖，避免与环境/ini 配置混淆
    config.attributes["url_override"] = url
    return config


def run_migrations(database_url: str | None = None) -> None:
    command.upgrade(build_alembic_config(database_url), "head")
