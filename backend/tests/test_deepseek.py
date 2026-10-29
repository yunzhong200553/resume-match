"""DeepSeek 的请求契约、错误处理和确认式改写；不访问外部网络。"""

from __future__ import annotations

import json
from copy import deepcopy

import httpx
import pytest

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.services.analysis.deepseek import DeepSeekProvider, complete_json, rewrite_content
from tests.fixtures import sample_document_dict

JD = "负责 Python 后端服务和 REST API 开发，熟悉 FastAPI 与 SQL 数据库，能够根据真实业务场景设计接口并参与团队协作和测试。"


@pytest.fixture
def deepseek_http(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(settings, "deepseek_api_key", "test-only-placeholder")
    monkeypatch.setattr(settings, "analysis_provider", "deepseek")

    def install(handler):
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))

    return install


def _response(payload, *, finish_reason="stop"):
    return httpx.Response(200, json={"choices": [{"finish_reason": finish_reason, "message": {"content": json.dumps(payload, ensure_ascii=False)}}]})


def _score(document):
    return {
        "overallScore": 78, "scoreLevel": "medium", "summary": "已有后端经历，但缺少部分岗位要求的证据。",
        "scoreBreakdown": [
            {"dimension": name, "weight": weight, "score": score, "reason": "根据已提供经历评分。"}
            for name, weight, score in [
                ("coreRequirements", 40, 32), ("experienceEvidence", 30, 24),
                ("skillsCoverage", 20, 16), ("presentationQuality", 10, 6),
            ]
        ],
        "itemMatches": [
            {"sectionId": section["id"], "itemId": item["id"], "score": 86, "level": "high", "reason": "存在相关技术证据。", "matchedRequirements": ["Python"]}
            for section in document["sections"] for item in section["items"]
        ],
        "missingRequirements": [],
    }


def test_real_provider_numeric_scores_and_redacted_request(deepseek_http):
    seen = []
    document = sample_document_dict()
    document["basicInfo"] = {"jobTarget": "后端"}
    document["sections"][1]["items"][0]["content"] += " 联系 test@example.com、13800000000"

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        data = json.loads(body["messages"][1]["content"])["data"]
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer test-only-placeholder"
        return _response(_score(data["document"]))

    deepseek_http(handler)
    result = DeepSeekProvider("scoreAgent").analyze(document=document, jd_text=JD)
    assert result["overallScore"] == 78
    assert len(result["itemMatches"]) == sum(len(section["items"]) for section in document["sections"])
    assert all(match["score"] == 86 for match in result["itemMatches"])
    sent = json.dumps(seen, ensure_ascii=False)
    assert "test@example.com" not in sent and "13800000000" not in sent
    assert "test-only-placeholder" not in sent
    assert seen[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("status,expected", [(401, "密钥无效"), (402, "余额不足"), (429, "频率过高"), (503, "HTTP 503")])
def test_api_failures_are_explicit_and_never_leak_provider_body(deepseek_http, status, expected):
    deepseek_http(lambda _: httpx.Response(status, text="sensitive-upstream-content"))
    with pytest.raises(AppError) as caught:
        complete_json(instruction="JSON", data={}, schema={})
    assert expected in caught.value.message
    assert "sensitive-upstream-content" not in caught.value.message


def test_api_timeout_is_not_reported_as_success(deepseek_http):
    def timeout(request):
        raise httpx.ReadTimeout("private connection details", request=request)
    deepseek_http(timeout)
    with pytest.raises(AppError) as caught:
        complete_json(instruction="JSON", data={}, schema={})
    assert caught.value.code is ErrorCode.ANALYSIS_TIMEOUT


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"choices": []}),
    _response({"rewritten": "text"}, finish_reason="length"),
    httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]}),
])
def test_malformed_or_truncated_response_is_rejected(deepseek_http, response):
    deepseek_http(lambda _: response)
    with pytest.raises(AppError):
        complete_json(instruction="JSON", data={}, schema={})


@pytest.mark.parametrize("invalid", ["missing", "out-of-range", "missing-score", "invalid-weight", "duplicate"])
def test_scoring_requires_valid_number_for_every_item(deepseek_http, invalid):
    document = sample_document_dict()
    payload = _score(document)
    if invalid == "missing":
        payload["itemMatches"].pop()
    elif invalid == "out-of-range":
        payload["itemMatches"][0]["score"] = 101
    elif invalid == "missing-score":
        payload["itemMatches"][0].pop("score")
    elif invalid == "invalid-weight":
        payload["scoreBreakdown"][0]["weight"] = 41
    else:
        payload["itemMatches"].append(deepcopy(payload["itemMatches"][0]))
    deepseek_http(lambda _: _response(payload))
    with pytest.raises(AppError):
        DeepSeekProvider("scoreAgent").analyze(document=document, jd_text=JD)


def test_scoring_derives_labels_and_total_from_actual_numeric_scores(deepseek_http):
    document = sample_document_dict()
    payload = _score(document)
    payload["overallScore"] = 99
    payload["scoreLevel"] = "high"
    payload["itemMatches"][0]["score"] = 55
    payload["itemMatches"][0]["level"] = "medium"
    deepseek_http(lambda _: _response(payload))

    result = DeepSeekProvider("scoreAgent").analyze(document=document, jd_text=JD)

    assert result["overallScore"] == 78
    assert result["scoreLevel"] == "medium"
    assert result["itemMatches"][0]["score"] == 55
    assert result["itemMatches"][0]["level"] == "low"


def test_rewrite_blocks_invented_numeric_results(deepseek_http):
    deepseek_http(lambda _: _response({"rewritten": "负责接口开发，性能提升 90%。", "explanation": "突出成果。"}))
    with pytest.raises(AppError, match="未提供的数字"):
        rewrite_content(fields={}, content="负责接口开发。", jd_text=JD, advice="突出职责。")


def test_missing_key_is_detected_before_task_creation(client, resume_factory, monkeypatch):
    _, version_id = resume_factory()
    monkeypatch.setattr(settings, "analysis_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    response = client.post("/api/analyses", json={"resumeVersionId": version_id, "jdText": JD})
    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.json()["error"]["message"]
    config = client.get("/api/analyses/configuration").json()["data"]
    assert config == {"provider": "deepseek", "model": settings.deepseek_model, "configured": False, "demo": False}


def test_analysis_rewrite_preview_and_confirm_end_to_end(client, resume_factory, deepseek_http):
    document = sample_document_dict()
    resume_id, version_id = resume_factory(document)
    calls = []

    def handler(request):
        task = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(task)
        data = task["data"]
        properties = task["schema"]["properties"]
        if "overallScore" in properties:
            return _response(_score(data["document"]))
        if "suggestions" in properties:
            item = data["document"]["sections"][1]["items"][0]
            return _response({"suggestions": [{
                "sectionId": "section_experience", "itemId": item["id"], "targetField": "content",
                "original": item["content"], "suggested": "参与订单系统重构，优化接口响应，平均响应时间下降 40%；",
                "reason": "突出已有职责与成果。",
            }]})
        return _response({"rewritten": "参与订单系统接口重构，平均响应时间下降 40%；", "explanation": "保留真实成果，明确接口职责。"})

    deepseek_http(handler)
    created = client.post("/api/analyses", json={"resumeVersionId": version_id, "jdText": JD})
    result = client.get(f"/api/analyses/{created.json()['data']['id']}").json()["data"]
    assert result["status"] == "completed", result
    suggestion = result["suggestions"][0]
    original = document["sections"][1]["items"][0]["content"]
    before = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]["document"]
    rewrite = client.post(f"/api/suggestions/{suggestion['id']}/rewrite", json={"currentContent": original})
    assert rewrite.status_code == 200, rewrite.text
    proposal = rewrite.json()["data"]
    assert proposal["rewritten"] != original
    after_preview = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]["document"]
    assert after_preview == before
    unchanged = client.get(f"/api/analyses/{result['id']}").json()["data"]["suggestions"][0]
    assert unchanged["status"] == "pending"
    saved_at = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]["updatedAt"]
    confirmed = client.post(f"/api/suggestions/{suggestion['id']}/confirm", json={
        "original": proposal["original"], "replacement": proposal["rewritten"], "document": after_preview, "expectedUpdatedAt": saved_at,
    })
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["draft"]["document"]["sections"][1]["items"][0]["content"] == proposal["rewritten"]
    fetched = client.get(f"/api/resumes/{resume_id}").json()["data"]
    assert fetched["latestAnalysis"]["id"] == result["id"]
    assert len(fetched["versions"]) == 1
    repeated = client.post(f"/api/suggestions/{suggestion['id']}/confirm", json={
        "original": original, "replacement": proposal["rewritten"], "document": after_preview, "expectedUpdatedAt": saved_at,
    })
    assert repeated.status_code == 409
    assert len(calls) == 3


def test_confirmation_rejects_stale_original_without_overwriting(client, resume_factory):
    resume_id, version_id = resume_factory()
    analysis_id = client.post("/api/analyses", json={"resumeVersionId": version_id, "jdText": JD}).json()["data"]["id"]
    suggestion = client.get(f"/api/analyses/{analysis_id}").json()["data"]["suggestions"][0]
    draft = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]
    current = draft["document"]
    current["sections"][1]["items"][0]["content"] = "人工刚更新的正文。"
    client.put(f"/api/resumes/{resume_id}/draft", json={"document": current})
    response = client.post(f"/api/suggestions/{suggestion['id']}/confirm", json={
        "original": suggestion["original"], "replacement": "旧 AI 改写", "document": current, "expectedUpdatedAt": draft["updatedAt"],
    })
    assert response.status_code == 409
    assert client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]["document"] == current


def test_confirmation_does_not_overwrite_other_tab_edits(client, resume_factory):
    resume_id, version_id = resume_factory()
    analysis_id = client.post("/api/analyses", json={"resumeVersionId": version_id, "jdText": JD}).json()["data"]["id"]
    suggestion = client.get(f"/api/analyses/{analysis_id}").json()["data"]["suggestions"][0]
    stale = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]
    fresh = deepcopy(stale["document"])
    fresh["basicInfo"]["jobTarget"] = "另一个页面刚修改的目标岗位"
    client.put(f"/api/resumes/{resume_id}/draft", json={"document": fresh})
    response = client.post(f"/api/suggestions/{suggestion['id']}/confirm", json={
        "original": suggestion["original"], "replacement": "按建议改写的正文",
        "document": stale["document"], "expectedUpdatedAt": stale["updatedAt"],
    })
    assert response.status_code == 409
    assert client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]["document"]["basicInfo"]["jobTarget"] == fresh["basicInfo"]["jobTarget"]
