"""简历、草稿与版本接口测试：A-05 与契约异常。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.models import Draft
from app.schemas.resume import VersionSource
from app.services import resume_service, version_service
from tests.fixtures import sample_document_dict


def test_create_resume_returns_draft(client: TestClient) -> None:
    response = client.post("/api/resumes", json={"title": "我的简历"})

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["resume"]["title"] == "我的简历"
    assert data["resume"]["latestVersion"] == 0
    assert data["draft"]["document"]["sections"] == []
    assert data["versions"] == []


def test_create_resume_requires_title(client: TestClient) -> None:
    response = client.post("/api/resumes", json={"title": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_resume_accepts_basic_info(client: TestClient) -> None:
    response = client.post(
        "/api/resumes",
        json={
            "title": "带基本信息",
            "basicInfo": {"name": "李小明", "jobTarget": "后端开发工程师"},
        },
    )

    assert response.status_code == 201
    draft = response.json()["data"]["draft"]["document"]
    assert draft["basicInfo"]["name"] == "李小明"
    assert draft["basicInfo"]["jobTarget"] == "后端开发工程师"


def test_list_resumes_returns_created_items(client: TestClient, resume_factory) -> None:
    resume_factory(title="第一份")
    resume_factory(title="第二份")

    response = client.get("/api/resumes")

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()["data"]["items"]}
    assert titles == {"第一份", "第二份"}


def test_resume_not_found(client: TestClient) -> None:
    response = client.get("/api/resumes/resume_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESUME_NOT_FOUND"


def test_draft_rejects_invalid_order(client: TestClient) -> None:
    resume_id = client.post("/api/resumes", json={"title": "排序校验"}).json()["data"][
        "resume"
    ]["id"]
    document = sample_document_dict()
    document["sections"][1]["order"] = 0

    response = client.put(f"/api/resumes/{resume_id}/draft", json={"document": document})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["errors"]


def test_draft_rejects_unknown_type(client: TestClient) -> None:
    resume_id = client.post("/api/resumes", json={"title": "类型校验"}).json()["data"][
        "resume"
    ]["id"]
    document = sample_document_dict()
    document["sections"][0]["type"] = "hobby"

    response = client.put(f"/api/resumes/{resume_id}/draft", json={"document": document})

    assert response.status_code == 422


def test_a05_draft_stays_editable_after_version_created(client: TestClient, resume_factory) -> None:
    resume_id, version_id = resume_factory()

    # 已创建的版本内容保持原样
    original = client.get(f"/api/resume-versions/{version_id}").json()["data"]
    assert original["document"]["basicInfo"]["name"] == "李小明"
    assert original["document"]["sections"][2]["items"][0]["fields"]["name"] == "ResumeMatch"

    # 草稿继续修改
    document = sample_document_dict()
    document["basicInfo"]["name"] = "李小明（改）"
    document["sections"][2]["items"][0]["content"] = "改写后的描述。"
    updated = client.put(f"/api/resumes/{resume_id}/draft", json={"document": document})
    assert updated.status_code == 200

    detail = client.get(f"/api/resumes/{resume_id}").json()["data"]
    assert detail["draft"]["document"]["basicInfo"]["name"] == "李小明（改）"
    assert detail["draft"]["document"]["sections"][2]["items"][0]["content"] == "改写后的描述。"
    assert len(detail["versions"]) == 1

    # 版本快照不受草稿影响
    snapshot = client.get(f"/api/resume-versions/{version_id}").json()["data"]
    assert snapshot["document"]["basicInfo"]["name"] == "李小明"
    assert "项目背景" in snapshot["document"]["sections"][2]["items"][0]["content"]


def test_draft_rejects_order_gaps(client: TestClient) -> None:
    """契约要求 order 从 0 开始且连续，存在断档时不能保存。"""

    resume_id = client.post("/api/resumes", json={"title": "排序断档"}).json()["data"]["resume"][
        "id"
    ]
    document = sample_document_dict()
    document["sections"][0]["order"] = 3
    document["sections"][1]["order"] = 8

    response = client.put(f"/api/resumes/{resume_id}/draft", json={"document": document})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_version_chain_records_parent_and_source(client: TestClient, resume_factory) -> None:
    resume_id, first_version_id = resume_factory()

    document = sample_document_dict()
    document["sections"][2]["items"][0]["content"] = "优化后的描述。"
    response = client.post(
        f"/api/resumes/{resume_id}/versions",
        json={
            "baseVersionId": first_version_id,
            "source": "optimized",
            "document": document,
        },
    )

    assert response.status_code == 201
    created = response.json()["data"]
    assert created["version"] == 2
    assert created["parentVersionId"] == first_version_id
    assert created["source"] == "optimized"

    listed = client.get(f"/api/resumes/{resume_id}/versions").json()["data"]["items"]
    assert [item["version"] for item in listed] == [1, 2]


def test_version_created_from_draft_without_document(client: TestClient, resume_factory) -> None:
    resume_id, _ = resume_factory(create_version=False)

    response = client.post(f"/api/resumes/{resume_id}/versions", json={"source": "import"})

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["source"] == "import"
    assert payload["version"] == 1
    assert payload["parentVersionId"] is None


def test_version_without_draft_requires_document(client: TestClient, session_factory) -> None:
    resume_id = client.post("/api/resumes", json={"title": "空草稿"}).json()["data"]["resume"]["id"]
    with session_factory() as session:
        session.execute(delete(Draft).where(Draft.resume_id == resume_id))
        session.commit()

    response = client.post(f"/api/resumes/{resume_id}/versions", json={"source": "manual"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_version_returns_404(client: TestClient) -> None:
    response = client.get("/api/resume-versions/version_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VERSION_NOT_FOUND"


def test_version_must_belong_to_resume(client: TestClient, resume_factory) -> None:
    _, version_id = resume_factory()
    other_resume_id = client.post("/api/resumes", json={"title": "另一份"}).json()["data"][
        "resume"
    ]["id"]

    response = client.put(
        f"/api/resumes/{other_resume_id}/draft",
        json={"document": sample_document_dict(), "baseVersionId": version_id},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VERSION_NOT_FOUND"


def test_version_snapshot_is_immutable_in_orm(db_session: Session) -> None:
    resume = resume_service.create_resume(db_session, title="不可变校验")
    version = version_service.create_version(
        db_session,
        resume_id=resume.id,
        source=VersionSource.MANUAL,
        document=resume_service.get_draft_document(db_session, resume.id),
    )

    version.source = "import"
    with pytest.raises(AppError) as exc_info:
        db_session.commit()

    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR
    assert "不可修改" in exc_info.value.message
    db_session.rollback()


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/resumes", headers={"X-Request-Id": "req_custom"})

    assert response.headers["X-Request-Id"] == "req_custom"
    assert response.json()["requestId"] == "req_custom"


def test_unknown_route_uses_error_contract(client: TestClient) -> None:
    response = client.get("/api/unknown-endpoint")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "HTTP_ERROR"
    assert "requestId" in body
