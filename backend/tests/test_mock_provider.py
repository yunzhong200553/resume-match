"""双分析 Provider 的固定数据契约测试。"""

from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCode
from app.schemas.analysis import ScoreProviderResult, SuggestionProviderResult
from app.schemas.resume_document import ResumeDocument
from app.services.analysis import get_providers
from tests.fixtures import sample_document_dict


def test_mock_providers_output_matches_contract() -> None:
    score_provider, suggestion_provider = get_providers("mock")
    document_payload = sample_document_dict()

    score = ScoreProviderResult.model_validate(
        score_provider.analyze(document=document_payload, jd_text="任意 JD")
    )
    suggestions = SuggestionProviderResult.model_validate(
        suggestion_provider.analyze(document=document_payload, jd_text="任意 JD")
    )

    document = ResumeDocument.model_validate(document_payload)
    for match in score.item_matches:
        assert document.find_item(match.section_id, match.item_id) is not None
    for suggestion in suggestions.suggestions:
        found = document.find_item(suggestion.section_id, suggestion.item_id)
        assert found is not None
        assert suggestion.original == found[1].content


def test_mock_providers_have_distinct_names() -> None:
    score_provider, suggestion_provider = get_providers("mock")

    assert score_provider.name == "scoreAgent"
    assert suggestion_provider.name == "suggestionAgent"


def test_coze_providers_are_explicitly_unavailable() -> None:
    with pytest.raises(AppError) as exc_info:
        get_providers("coze")

    assert exc_info.value.code is ErrorCode.ANALYSIS_PROVIDER_ERROR


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(AppError) as exc_info:
        get_providers("openai")

    assert exc_info.value.code is ErrorCode.ANALYSIS_PROVIDER_ERROR
    assert "openai" in exc_info.value.message


def test_module_a_still_works_with_analysis_routes(client) -> None:
    """I-01：分析路由启用后模块 A 仍完全可用。"""

    missing = client.get("/api/analyses/analysis_1")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    response = client.post("/api/resumes", json={"title": "无分析依赖"})
    assert response.status_code == 201
