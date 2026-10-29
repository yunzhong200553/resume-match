"""建议接受、拒绝和编辑接口测试。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import AppError, ErrorCode
from app.db.models import Analysis, Draft, Suggestion
from app.services.analysis import service
from tests.test_analysis_api import JD_TEXT


def _create_suggestion(client, resume_factory):
    resume_id, version_id = resume_factory()
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": JD_TEXT},
    )
    analysis = client.get(
        f"/api/analyses/{created.json()['data']['id']}"
    ).json()["data"]
    assert analysis["status"] == "completed"
    return resume_id, version_id, analysis["suggestions"][0]


@pytest.mark.parametrize(
    ("payload", "expected_text", "expected_edited_text"),
    [
        (
            {"status": "accepted", "editedText": None},
            "突出已有职责并优化条目表达。",
            None,
        ),
        (
            {"status": "rejected", "editedText": None},
            "参与订单系统重构，接口平均响应时间下降 40%；",
            None,
        ),
        (
            {"status": "edited", "editedText": "  用户确认后的表达  "},
            "用户确认后的表达",
            "用户确认后的表达",
        ),
    ],
)
def test_update_suggestion_only_changes_draft(
    client,
    resume_factory,
    payload,
    expected_text,
    expected_edited_text,
) -> None:
    resume_id, version_id, suggestion = _create_suggestion(client, resume_factory)
    original_version = client.get(f"/api/resume-versions/{version_id}").json()["data"]

    response = client.patch(f"/api/suggestions/{suggestion['id']}", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == payload["status"]
    assert data["editedText"] == expected_edited_text
    resume = client.get(f"/api/resumes/{resume_id}").json()["data"]
    draft = resume["draft"]
    assert draft["baseVersionId"] == version_id
    draft_items = {
        item["id"]: item
        for section in draft["document"]["sections"]
        for item in section["items"]
    }
    assert draft_items[suggestion["itemId"]]["content"] == expected_text
    current_version = client.get(f"/api/resume-versions/{version_id}").json()["data"]
    assert current_version["document"] == original_version["document"]


def test_update_suggestion_rejects_repeated_transition(
    client, resume_factory
) -> None:
    _, _, suggestion = _create_suggestion(client, resume_factory)
    first = client.patch(
        f"/api/suggestions/{suggestion['id']}",
        json={"status": "accepted", "editedText": None},
    )
    assert first.status_code == 200

    repeated = client.patch(
        f"/api/suggestions/{suggestion['id']}",
        json={"status": "rejected", "editedText": None},
    )

    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "SUGGESTION_STATE_CONFLICT"


def test_update_suggestion_rejects_unknown_id(client) -> None:
    response = client.patch(
        "/api/suggestions/suggestion_missing",
        json={"status": "accepted", "editedText": None},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SUGGESTION_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "edited", "editedText": "   "},
        {"status": "accepted", "editedText": "不应存在"},
        {"status": "pending", "editedText": None},
    ],
)
def test_update_suggestion_rejects_invalid_payload(
    client, resume_factory, payload
) -> None:
    _, _, suggestion = _create_suggestion(client, resume_factory)

    response = client.patch(f"/api/suggestions/{suggestion['id']}", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_concurrent_suggestion_update_does_not_overwrite_draft(
    client, resume_factory, session_factory
) -> None:
    resume_id, version_id, first = _create_suggestion(client, resume_factory)
    with session_factory() as setup_session:
        analysis_id = setup_session.scalar(select(Analysis.id))
        setup_session.add(
            Suggestion(
                id="suggestion_concurrent",
                analysis_id=analysis_id,
                section_id="section_project",
                item_id="item_project_1",
                target_field="content",
                original="项目背景：面向求职场景的简历匹配系统。\n项目内容：负责简历解析、版本管理和导出服务。",
                suggested="优化后的项目描述。",
                reason="并发更新测试。",
                status="pending",
                edited_text=None,
            )
        )
        setup_session.commit()

    with session_factory() as stale_session:
        stale_session.get(Suggestion, "suggestion_concurrent")
        stale_draft = stale_session.scalar(
            select(Draft).where(Draft.resume_id == resume_id)
        )
        assert stale_draft is not None

        first_update = client.patch(
            f"/api/suggestions/{first['id']}",
            json={"status": "accepted", "editedText": None},
        )
        assert first_update.status_code == 200

        with pytest.raises(AppError) as exc_info:
            service.update_suggestion(
                stale_session,
                "suggestion_concurrent",
                status="accepted",
                edited_text=None,
            )

    assert exc_info.value.code is ErrorCode.SUGGESTION_STATE_CONFLICT
    with session_factory() as verification_session:
        second = verification_session.get(Suggestion, "suggestion_concurrent")
        draft = verification_session.scalar(
            select(Draft).where(Draft.resume_id == resume_id)
        )
        assert second is not None and second.status == "pending"
        assert draft is not None and draft.base_version_id == version_id
        items = {
            item["id"]: item
            for section in draft.document["sections"]
            for item in section["items"]
        }
        assert items[first["itemId"]]["content"] == first["suggested"]
        assert items["item_project_1"]["content"] != "优化后的项目描述。"