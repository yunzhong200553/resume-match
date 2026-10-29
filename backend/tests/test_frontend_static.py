"""The one-click application serves built UI and API on one local port."""

from fastapi.testclient import TestClient

import app.main as main
from app.core.config import settings


def test_built_frontend_and_api_share_one_server(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><title>ResumeMatch</title></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ResumeMatch');", encoding="utf-8")
    (tmp_path / ".env").write_text("PRIVATE_PLACEHOLDER_ONLY", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    monkeypatch.setattr(settings, "auto_migrate", False)
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    with TestClient(main.create_app()) as client:
        assert "<title>ResumeMatch</title>" in client.get("/").text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/health").json()["data"] == {"service": "resume-match", "status": "ok"}
        assert client.get("/api/export-templates").status_code == 200
        assert client.get("/.env").status_code == 404
        assert client.get("/backend/app/main.py").status_code == 404


def test_api_can_start_before_frontend_is_built(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path / "missing-dist")
    monkeypatch.setattr(settings, "auto_migrate", False)
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    with TestClient(main.create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 404
