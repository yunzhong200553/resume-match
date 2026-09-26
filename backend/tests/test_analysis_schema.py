"""JD 分析 Schema 的跨字段约束测试。"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.analysis import Analysis, ProviderState, Suggestion


PROVIDERS = {
    "scoreAgent": {
        "status": "succeeded",
        "attempts": 1,
        "errorCode": None,
        "errorMessage": None,
    },
    "suggestionAgent": {
        "status": "succeeded",
        "attempts": 1,
        "errorCode": None,
        "errorMessage": None,
    },
}

SCORE_BREAKDOWN = [
    {"dimension": "coreRequirements", "weight": 40, "score": 32, "reason": "核心要求。"},
    {"dimension": "experienceEvidence", "weight": 30, "score": 24, "reason": "经历证据。"},
    {"dimension": "skillsCoverage", "weight": 20, "score": 16, "reason": "技能覆盖。"},
    {"dimension": "presentationQuality", "weight": 10, "score": 6, "reason": "表达质量。"},
]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "status": "failed",
            "attempts": 1,
            "errorCode": None,
            "errorMessage": None,
        },
        {
            "status": "succeeded",
            "attempts": 1,
            "errorCode": "SHOULD_BE_NULL",
            "errorMessage": "不应存在",
        },
    ],
)
def test_provider_state_rejects_inconsistent_error_fields(payload) -> None:
    with pytest.raises(ValidationError):
        ProviderState.model_validate(payload)


def test_analysis_rejects_invalid_frozen_score_dimensions() -> None:
    invalid_breakdown = [dict(item) for item in SCORE_BREAKDOWN]
    invalid_breakdown[0]["weight"] = 39

    with pytest.raises(ValidationError):
        Analysis.model_validate(
            {
                "id": "analysis_1",
                "resumeVersionId": "version_1",
                "status": "completed",
                "jdText": "岗位描述",
                "overallScore": 78,
                "scoreLevel": "medium",
                "summary": "分析摘要",
                "scoreBreakdown": invalid_breakdown,
                "itemMatches": [],
                "missingRequirements": [],
                "suggestions": [],
                "providers": PROVIDERS,
                "createdAt": datetime(2026, 9, 26),
                "updatedAt": datetime(2026, 9, 26),
                "completedAt": datetime(2026, 9, 26),
            }
        )


def test_analysis_rejects_score_total_mismatch() -> None:
    invalid_breakdown = [dict(item) for item in SCORE_BREAKDOWN]
    invalid_breakdown[0]["score"] = 31

    with pytest.raises(ValidationError):
        Analysis.model_validate(
            {
                "id": "analysis_1",
                "resumeVersionId": "version_1",
                "status": "completed",
                "jdText": "岗位描述",
                "overallScore": 78,
                "scoreLevel": "medium",
                "summary": "分析摘要",
                "scoreBreakdown": invalid_breakdown,
                "itemMatches": [],
                "missingRequirements": [],
                "suggestions": [],
                "providers": PROVIDERS,
                "createdAt": datetime(2026, 9, 26),
                "updatedAt": datetime(2026, 9, 26),
                "completedAt": datetime(2026, 9, 26),
            }
        )


def test_suggestion_trims_edited_text_and_normalizes_timestamps() -> None:
    suggestion = Suggestion.model_validate(
        {
            "id": "suggestion_1",
            "analysisId": "analysis_1",
            "sectionId": "section_1",
            "itemId": "item_1",
            "targetField": "content",
            "original": "原文",
            "suggested": "建议文本",
            "reason": "修改理由",
            "status": "edited",
            "editedText": "  用户编辑文本  ",
            "createdAt": datetime(2026, 9, 26),
            "updatedAt": datetime(2026, 9, 26),
        }
    )

    assert suggestion.edited_text == "用户编辑文本"
    assert suggestion.created_at.utcoffset() is not None
    assert suggestion.updated_at.utcoffset() is not None