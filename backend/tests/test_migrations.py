"""数据迁移测试：Alembic 是表结构的唯一来源。"""

from __future__ import annotations

import json

from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db.migrate import build_alembic_config, run_migrations

EXPECTED_TABLES = {
    "resumes",
    "resume_versions",
    "drafts",
    "analyses",
    "suggestions",
    "export_records",
    "resume_layouts",
    "alembic_version",
}


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


def test_suggestion_target_is_unique_per_analysis(tmp_path) -> None:
    url = _url(tmp_path)
    run_migrations(url)

    engine = create_engine(url)
    try:
        constraints = inspect(engine).get_unique_constraints("suggestions")
    finally:
        engine.dispose()
    names = {constraint["name"] for constraint in constraints}
    assert "uq_suggestion_target" in names


def test_named_layout_storage_and_export_link(tmp_path) -> None:
    url = _url(tmp_path)
    run_migrations(url)
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        constraints = inspector.get_unique_constraints("resume_layouts")
        columns = {column["name"] for column in inspector.get_columns("export_records")}
        foreign_keys = inspector.get_foreign_keys("export_records")
    finally:
        engine.dispose()
    assert "uq_resume_layout_name" in {constraint["name"] for constraint in constraints}
    assert "layout_id" in columns
    assert any(key["referred_table"] == "resume_layouts" for key in foreign_keys)


def test_draft_tracks_owning_analysis(tmp_path) -> None:
    url = _url(tmp_path)
    run_migrations(url)

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("drafts")}
        foreign_keys = inspector.get_foreign_keys("drafts")
    finally:
        engine.dispose()

    assert "analysis_id" in columns
    assert any(
        key["constrained_columns"] == ["analysis_id"]
        and key["referred_table"] == "analyses"
        for key in foreign_keys
    )


def test_upgrade_from_0002_preserves_existing_draft(tmp_path) -> None:
    url = _url(tmp_path)
    config = build_alembic_config(url)
    command.upgrade(config, "0002_analysis")
    engine = create_engine(url)
    now = "2026-09-30 00:00:00"
    document = {"basicInfo": {"name": "迁移前草稿"}, "sections": []}
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO resumes (id, title, created_at, updated_at) "
                    "VALUES (:id, :title, :created_at, :updated_at)"
                ),
                {
                    "id": "resume_existing",
                    "title": "已有简历",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO drafts "
                    "(id, resume_id, base_version_id, document, updated_at) "
                    "VALUES (:id, :resume_id, :base_version_id, :document, :updated_at)"
                ),
                {
                    "id": "draft_existing",
                    "resume_id": "resume_existing",
                    "base_version_id": "version_existing",
                    "document": json.dumps(document, ensure_ascii=False),
                    "updated_at": now,
                },
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT base_version_id, analysis_id, document "
                    "FROM drafts WHERE id = 'draft_existing'"
                )
            ).one()
    finally:
        engine.dispose()

    assert row.base_version_id == "version_existing"
    assert row.analysis_id is None
    assert json.loads(row.document) == document
