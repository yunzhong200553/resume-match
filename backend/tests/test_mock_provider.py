"""分析适配层契约测试（Mock 与 Coze 共用同一标准结构）。"""

from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.schemas.resume_document import ResumeDocument
from app.services.analysis import get_provider
from tests.fixtures import sample_document_dict

VALID_LEVELS = {"high", "medium", "low"}
VALID_STATUSES = {"pending", "accepted", "rejected", "edited"}


def test_mock_provider_output_matches_contract() -> None:
    provider = get_provider("mock")
    document_payload = sample_document_dict()

    result = provider.analyze(
        document=document_payload,
        jd_text="负责后端服务开发，熟悉 Python、FastAPI 和数据库设计。",
    )

    assert result["status"] == "completed"
    assert isinstance(result["overallScore"], int)
    assert 0 <= result["overallScore"] <= 100

    assert {match["level"] for match in result["itemMatches"]} <= VALID_LEVELS
    assert {suggestion["status"] for suggestion in result["suggestions"]} <= VALID_STATUSES

    document = ResumeDocument.model_validate(document_payload)
    for match in result["itemMatches"]:
        assert document.find_item(match["sectionId"], match["itemId"]) is not None
    for suggestion in result["suggestions"]:
        assert document.find_item(suggestion["sectionId"], suggestion["itemId"]) is not None

    for missing in result["missingRequirements"]:
        assert missing["requirement"] and missing["reason"]


def test_mock_provider_survives_empty_document() -> None:
    provider = get_provider("mock")

    result = provider.analyze(document={"sections": []}, jd_text="任意 JD")

    assert result["status"] == "completed"
    assert result["itemMatches"]


def test_coze_provider_is_explicitly_unavailable() -> None:
    with pytest.raises(AppError) as exc_info:
        get_provider("coze")

    assert exc_info.value.code is ErrorCode.ANALYSIS_PROVIDER_ERROR


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        get_provider("openai")

    assert exc_info.value.code is ErrorCode.ANALYSIS_PROVIDER_ERROR
    assert "openai" in exc_info.value.message


def test_module_a_has_no_analysis_routes(client) -> None:
    """I-01：禁用分析能力后模块 A 仍完全可用。"""

    assert client.get("/api/analyses/analysis_1").status_code == 404
    response = client.post("/api/resumes", json={"title": "无分析依赖"})
    assert response.status_code == 201
