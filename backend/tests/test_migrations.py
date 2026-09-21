"""数据迁移测试：Alembic 是表结构的唯一来源。"""

from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, inspect

from app.db.migrate import build_alembic_config, run_migrations

EXPECTED_TABLES = {"resumes", "resume_versions", "drafts", "export_records", "alembic_version"}


def _url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"


def test_upgrade_head_creates_all_tables(tmp_path) -> None:
    url = _url(tmp_path)

    run_migrations(url)

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert EXPECTED_TABLES <= tables


def test_migration_can_downgrade_to_base(tmp_path) -> None:
    url = _url(tmp_path)
    run_migrations(url)

    command.downgrade(build_alembic_config(url), "base")

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables == {"alembic_version"}


def test_resume_version_number_is_unique_per_resume(tmp_path) -> None:
    url = _url(tmp_path)
    run_migrations(url)

    engine = create_engine(url)
    try:
        constraints = inspect(engine).get_unique_constraints("resume_versions")
    finally:
        engine.dispose()
    names = {constraint["name"] for constraint in constraints}
    assert "uq_resume_version_number" in names
