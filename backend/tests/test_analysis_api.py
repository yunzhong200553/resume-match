"""JD 分析创建与查询接口测试。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import func, select

from app.core.errors import AppError, ErrorCode
from app.db.models import Analysis as AnalysisRecord
from app.services.analysis import service
from app.services.analysis.provider import get_providers


JD_TEXT = "负责 Python 后端服务与 REST API 开发，参与数据库设计和性能优化，熟悉 FastAPI、SQL 和 Docker。"


def _assert_aware_timestamp(value: str) -> None:
    assert datetime.fromisoformat(value).utcoffset() is not None


class FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    def analyze(self, *, document: dict[str, Any], jd_text: str) -> dict[str, Any]:
        del document, jd_text
        raise RuntimeError("provider failed")


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
    _assert_aware_timestamp(created_data["createdAt"])
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
    assert data["status"] == "completed"
    assert data["overallScore"] == 78
    assert data["scoreLevel"] == "medium"
    assert len(data["scoreBreakdown"]) == 4
    assert data["itemMatches"]
    assert data["missingRequirements"]
    assert data["suggestions"]
    assert data["completedAt"] is not None
    _assert_aware_timestamp(data["createdAt"])
    _assert_aware_timestamp(data["updatedAt"])
    _assert_aware_timestamp(data["completedAt"])
    _assert_aware_timestamp(data["suggestions"][0]["createdAt"])
    _assert_aware_timestamp(data["suggestions"][0]["updatedAt"])
    assert data["providers"]["scoreAgent"]["status"] == "succeeded"
    assert data["providers"]["suggestionAgent"]["status"] == "succeeded"


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


@pytest.mark.parametrize("jd_text", [None, 123, ["岗"] * 100, {"text": "岗位" * 50}])
def test_create_analysis_rejects_non_string_jd(
    client, resume_factory, jd_text
) -> None:
    _, version_id = resume_factory()

    response = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": jd_text},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_analysis_rejects_unknown_id(client) -> None:
    response = client.get("/api/analyses/analysis_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_retry_reuses_analysis_and_only_runs_failed_provider(
    client, resume_factory, db_session, monkeypatch
) -> None:
    score_provider, suggestion_provider = get_providers("mock")
    monkeypatch.setattr(
        service,
        "get_providers",
        lambda: (score_provider, FailingProvider("suggestionAgent")),
    )
    _, version_id = resume_factory()
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": JD_TEXT},
    )
    analysis_id = created.json()["data"]["id"]
    before = client.get(f"/api/analyses/{analysis_id}").json()["data"]
    assert before["status"] == "partial_failed"

    monkeypatch.setattr(
        service,
        "get_providers",
        lambda: (score_provider, suggestion_provider),
    )
    retried = client.post(
        f"/api/analyses/{analysis_id}/retry",
        json={"targets": ["suggestionAgent"]},
    )

    assert retried.status_code == 202
    assert retried.json()["data"]["id"] == analysis_id
    assert retried.json()["data"]["retryingProviders"] == ["suggestionAgent"]
    after = client.get(f"/api/analyses/{analysis_id}").json()["data"]
    assert after["status"] == "completed"
    assert after["providers"]["scoreAgent"]["attempts"] == 1
    assert after["providers"]["suggestionAgent"]["attempts"] == 2
    assert len(after["suggestions"]) == 1
    count = db_session.scalar(select(func.count()).select_from(AnalysisRecord))
    assert count == 1


def test_retry_rejects_processing_analysis(client, resume_factory, monkeypatch) -> None:
    monkeypatch.setattr(service, "run_analysis", lambda *_args, **_kwargs: None)
    _, version_id = resume_factory()
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": JD_TEXT},
    )

    response = client.post(
        f"/api/analyses/{created.json()['data']['id']}/retry",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_IN_PROGRESS"


def test_retry_rejects_provider_that_did_not_fail(
    client, resume_factory
) -> None:
    _, version_id = resume_factory()
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": JD_TEXT},
    )

    response = client.post(
        f"/api/analyses/{created.json()['data']['id']}/retry",
        json={"targets": ["scoreAgent"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_RETRYABLE"


def test_retry_atomically_rejects_stale_concurrent_claim(
    client, resume_factory, session_factory, monkeypatch
) -> None:
    score_provider, _ = get_providers("mock")
    monkeypatch.setattr(
        service,
        "get_providers",
        lambda: (score_provider, FailingProvider("suggestionAgent")),
    )
    _, version_id = resume_factory()
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": JD_TEXT},
    )
    analysis_id = created.json()["data"]["id"]
    assert client.get(f"/api/analyses/{analysis_id}").json()["data"]["status"] == "partial_failed"

    with session_factory() as stale_session:
        stale = service.get_analysis(stale_session, analysis_id)
        assert stale.status == "partial_failed"
        monkeypatch.setattr(service, "run_analysis", lambda *_args, **_kwargs: None)
        claimed = client.post(
            f"/api/analyses/{analysis_id}/retry",
            json={"targets": ["suggestionAgent"]},
        )
        assert claimed.status_code == 202

        with pytest.raises(AppError) as exc_info:
            service.prepare_retry(stale_session, analysis_id, ["suggestionAgent"])

    assert exc_info.value.code is ErrorCode.ANALYSIS_IN_PROGRESS