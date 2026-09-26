"""双 Provider 执行与 Analysis 状态汇总测试。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.analysis import service

from tests.test_analysis_api import JD_TEXT


SCORE_RESULT = {
    "overallScore": 78,
    "scoreLevel": "medium",
    "summary": "简历与岗位要求中等偏高契合。",
    "scoreBreakdown": [
        {"dimension": "coreRequirements", "weight": 40, "score": 32, "reason": "核心要求有证据。"},
        {"dimension": "experienceEvidence", "weight": 30, "score": 24, "reason": "经历与岗位相关。"},
        {"dimension": "skillsCoverage", "weight": 20, "score": 16, "reason": "技能覆盖较好。"},
        {"dimension": "presentationQuality", "weight": 10, "score": 6, "reason": "表达基本清晰。"},
    ],
    "itemMatches": [
        {
            "sectionId": "section_experience",
            "itemId": "item_experience_1",
            "level": "high",
            "matchedRequirements": ["Python"],
            "reason": "条目包含相关技术。",
        }
    ],
    "missingRequirements": [],
}

SUGGESTION_RESULT = {
    "suggestions": [
        {
            "sectionId": "section_experience",
            "itemId": "item_experience_1",
            "targetField": "content",
            "original": "参与订单系统重构，接口平均响应时间下降 40%；",
            "suggested": "参与订单系统重构，并优化接口响应表现。",
            "reason": "保留已有事实并提高表达清晰度。",
        }
    ]
}


class StubProvider:
    def __init__(self, name: str, result: dict[str, Any] | None = None) -> None:
        self.name = name
        self.result = result

    def analyze(self, *, document: dict[str, Any], jd_text: str) -> dict[str, Any]:
        del document, jd_text
        if self.result is None:
            raise RuntimeError("provider failed")
        return deepcopy(self.result)


def _set_providers(monkeypatch, score_result, suggestion_result) -> None:
    monkeypatch.setattr(
        service,
        "get_providers",
        lambda: (
            StubProvider("scoreAgent", score_result),
            StubProvider("suggestionAgent", suggestion_result),
        ),
    )


def _create_and_fetch(client, resume_factory):
    _, version_id = resume_factory()
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": JD_TEXT},
    )
    assert created.status_code == 202
    return client.get(f"/api/analyses/{created.json()['data']['id']}").json()["data"]


def test_both_providers_succeed(client, resume_factory, monkeypatch) -> None:
    _set_providers(monkeypatch, SCORE_RESULT, SUGGESTION_RESULT)

    data = _create_and_fetch(client, resume_factory)

    assert data["status"] == "completed"
    assert data["overallScore"] == 78
    assert len(data["suggestions"]) == 1


def test_score_provider_failure_is_partial(client, resume_factory, monkeypatch) -> None:
    _set_providers(monkeypatch, None, SUGGESTION_RESULT)

    data = _create_and_fetch(client, resume_factory)

    assert data["status"] == "partial_failed"
    assert data["overallScore"] is None
    assert len(data["suggestions"]) == 1
    assert data["providers"]["scoreAgent"]["status"] == "failed"


def test_suggestion_provider_failure_is_partial(client, resume_factory, monkeypatch) -> None:
    _set_providers(monkeypatch, SCORE_RESULT, None)

    data = _create_and_fetch(client, resume_factory)

    assert data["status"] == "partial_failed"
    assert data["overallScore"] == 78
    assert data["suggestions"] == []
    assert data["providers"]["suggestionAgent"]["status"] == "failed"


def test_both_providers_fail(client, resume_factory, monkeypatch) -> None:
    _set_providers(monkeypatch, None, None)

    data = _create_and_fetch(client, resume_factory)

    assert data["status"] == "failed"
    assert data["overallScore"] is None
    assert data["suggestions"] == []


def test_invalid_score_fails_only_score_provider(client, resume_factory, monkeypatch) -> None:
    invalid_score = deepcopy(SCORE_RESULT)
    invalid_score["overallScore"] = 101
    _set_providers(monkeypatch, invalid_score, SUGGESTION_RESULT)

    data = _create_and_fetch(client, resume_factory)

    assert data["status"] == "partial_failed"
    assert data["providers"]["scoreAgent"]["errorCode"] == "INVALID_PROVIDER_RESPONSE"
    assert data["providers"]["suggestionAgent"]["status"] == "succeeded"


def test_unknown_item_id_fails_only_score_provider(client, resume_factory, monkeypatch) -> None:
    invalid_item = deepcopy(SCORE_RESULT)
    invalid_item["itemMatches"][0]["itemId"] = "item_missing"
    _set_providers(monkeypatch, invalid_item, SUGGESTION_RESULT)

    data = _create_and_fetch(client, resume_factory)

    assert data["status"] == "partial_failed"
    assert data["providers"]["scoreAgent"]["errorCode"] == "INVALID_PROVIDER_RESPONSE"
    assert data["providers"]["suggestionAgent"]["status"] == "succeeded"