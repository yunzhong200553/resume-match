"""pytest 公共夹具。

测试使用独立的临时 SQLite 文件与临时存储目录，
既不接触开发库，也不写入仓库内的 storage/。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BACKEND_DIR, REPO_ROOT, settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from tests.fixtures import sample_document_dict


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def db_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db_session(session_factory) -> Session:
    session: Session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def client(tmp_path, session_factory, monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    monkeypatch.setattr(settings, "assets_dir", BACKEND_DIR / "assets")
    monkeypatch.setattr(settings, "auto_migrate", False)
    monkeypatch.setattr(settings, "libreoffice_bin", "")

    app = create_app()

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def resume_factory(client):
    """创建简历 -> 保存草稿 -> 生成版本，返回 (resumeId, versionId)。"""

    def _create(
        document: dict | None = None, *, title: str = "测试简历", create_version: bool = True
    ):
        body = document or sample_document_dict()
        response = client.post("/api/resumes", json={"title": title})
        assert response.status_code == 201, response.text
        resume_id = response.json()["data"]["resume"]["id"]

        response = client.put(f"/api/resumes/{resume_id}/draft", json={"document": body})
        assert response.status_code == 200, response.text

        version_id = None
        if create_version:
            response = client.post(f"/api/resumes/{resume_id}/versions", json={"source": "manual"})
            assert response.status_code == 201, response.text
            version_id = response.json()["data"]["id"]
        return resume_id, version_id

    return _create
