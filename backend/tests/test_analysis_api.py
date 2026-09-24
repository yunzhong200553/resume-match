"""JD 分析创建与查询接口测试。"""

from __future__ import annotations


JD_TEXT = "负责 Python 后端服务与 REST API 开发，参与数据库设计和性能优化，熟悉 FastAPI、SQL 和 Docker。"


def test_create_and_get_processing_analysis(client, resume_factory) -> None:
    _, version_id = resume_factory()

    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": f"  {JD_TEXT}  "},
    )

    assert created.status_code == 202
    created_data = created.json()["data"]
    assert created_data["id"].startswith("analysis_")
    assert created_data["resumeVersionId"] == version_id
    assert created_data["status"] == "processing"
    assert created_data["providers"] == {
        "scoreAgent": {
            "status": "queued",
            "attempts": 0,
            "errorCode": None,
            "errorMessage": None,
        },
        "suggestionAgent": {
            "status": "queued",
            "attempts": 0,
            "errorCode": None,
            "errorMessage": None,
        },
    }

    fetched = client.get(f"/api/analyses/{created_data['id']}")

    assert fetched.status_code == 200
    data = fetched.json()["data"]
    assert data["jdText"] == JD_TEXT
    assert data["overallScore"] is None
    assert data["scoreLevel"] is None
    assert data["summary"] is None
    assert data["scoreBreakdown"] == []
    assert data["itemMatches"] == []
    assert data["missingRequirements"] == []
    assert data["suggestions"] == []
    assert data["completedAt"] is None


def test_duplicate_input_creates_independent_analyses(client, resume_factory) -> None:
    _, version_id = resume_factory()
    payload = {"resumeVersionId": version_id, "jdText": JD_TEXT}

    first = client.post("/api/analyses", json=payload)
    second = client.post("/api/analyses", json=payload)

    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["id"] != second.json()["data"]["id"]


def test_create_analysis_rejects_unknown_version(client) -> None:
    response = client.post(
        "/api/analyses",
        json={"resumeVersionId": "version_missing", "jdText": JD_TEXT},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VERSION_NOT_FOUND"


def test_create_analysis_rejects_short_jd(client, resume_factory) -> None:
    _, version_id = resume_factory()

    response = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": "  太短  "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "JD_TEXT_TOO_SHORT"


def test_create_analysis_rejects_long_jd(client, resume_factory) -> None:
    _, version_id = resume_factory()

    response = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": "岗" * 20_001},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "JD_TEXT_TOO_LONG"


def test_get_analysis_rejects_unknown_id(client) -> None:
    response = client.get("/api/analyses/analysis_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"