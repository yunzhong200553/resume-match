"""应用配置。

所有敏感配置（Coze Token 等）只允许通过环境变量或本机 ``.env`` 注入，
仓库内只保留 ``.env.example``。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'data' / 'resume_match.db').as_posix()}"


class Settings(BaseSettings):
    """进程级配置，字段名与 ``.env`` 变量名大小写不敏感映射。"""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = DEFAULT_DATABASE_URL
    storage_dir: Path = BACKEND_DIR / "storage"
    assets_dir: Path = BACKEND_DIR / "assets"

    max_upload_mb: int = 10
    libreoffice_bin: str = ""
    libreoffice_timeout_seconds: int = 120
    auto_migrate: bool = True

    #: 参考简历原件路径（含个人信息，不入库），仅模板构建脚本使用
    reference_resume_path: str = ""

    # 模块 B 预留，模块 A 不读取其值，仅保证配置项已就位
    analysis_provider: str = "mock"
    coze_bot_id: str = ""
    coze_api_token: str = ""

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def export_dir(self) -> Path:
        return self.storage_dir / "exports"

    @property
    def template_dir(self) -> Path:
        return self.assets_dir / "templates"

    @property
    def mock_dir(self) -> Path:
        return self.assets_dir / "mock"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for directory in (self.storage_dir, self.upload_dir, self.export_dir):
            directory.mkdir(parents=True, exist_ok=True)
        database_dir = sqlite_directory(self.database_url)
        if database_dir is not None:
            database_dir.mkdir(parents=True, exist_ok=True)


SQLITE_PREFIX = "sqlite:///"


def sqlite_directory(database_url: str) -> Path | None:
    """返回 SQLite 数据库文件所在目录（非 SQLite 或内存库时返回 None）。"""

    if not database_url.startswith(SQLITE_PREFIX):
        return None
    raw_path = database_url[len(SQLITE_PREFIX) :]
    if not raw_path or raw_path == ":memory:":
        return None
    return Path(raw_path).expanduser().resolve().parent


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
