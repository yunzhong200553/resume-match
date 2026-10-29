"""JD 分析到 optimized 版本及共享导出的端到端测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Draft
from app.services.analysis import service
from tests.test_analysis_api import JD_TEXT
from tests.test_export_api import TEMPLATE_ID, docx_text


def _create_completed_analysis(client, version_id: str) -> dict:
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": version_id, "jdText": JD_TEXT},
    )
    assert created.status_code == 202
    response = client.get(f"/api/analyses/{created.json()['data']['id']}")
    assert response.status_code == 200
    analysis = response.json()["data"]
    assert analysis["status"] == "completed"
    return analysis


def test_analysis_suggestion_persists_and_exports_optimized_version(
    client, resume_factory
) -> None:
    resume_id, base_version_id = resume_factory()
    original = client.get(f"/api/resume-versions/{base_version_id}").json()["data"]
    analysis = _create_completed_analysis(client, base_version_id)
    suggestion = analysis["suggestions"][0]

    accepted = client.patch(
        f"/api/suggestions/{suggestion['id']}",
        json={"status": "accepted", "editedText": None},
    )
    assert accepted.status_code == 200

    saved = client.post(f"/api/analyses/{analysis['id']}/versions")

    assert saved.status_code == 201
    optimized = saved.json()["data"]
    assert optimized["resumeId"] == resume_id
    assert optimized["version"] == 2
    assert optimized["parentVersionId"] == base_version_id
    assert optimized["source"] == "optimized"
    optimized_items = {
        item["id"]: item
        for section in optimized["document"]["sections"]
        for item in section["items"]
    }
    assert optimized_items[suggestion["itemId"]]["content"] == suggestion["suggested"]

    unchanged = client.get(f"/api/resume-versions/{base_version_id}").json()["data"]
    assert unchanged["document"] == original["document"]
    versions = client.get(f"/api/resumes/{resume_id}/versions").json()["data"]["items"]
    assert [(item["source"], item["parentVersionId"]) for item in versions] == [
        ("manual", None),
        ("optimized", base_version_id),
    ]

    exported = client.post(
        f"/api/resume-versions/{optimized['id']}/exports",
        json={"templateId": TEMPLATE_ID, "format": "docx"},
    )
    assert exported.status_code == 201
    download = client.get(exported.json()["data"]["downloadUrl"])
    assert download.status_code == 200
    assert suggestion["suggested"] in docx_text(download.content)


def test_suggestion_claims_draft_and_manual_save_releases_owner(
    client, resume_factory, session_factory
) -> None:
    resume_id, base_version_id = resume_factory()
    analysis = _create_completed_analysis(client, base_version_id)
    accepted = client.patch(
        f"/api/suggestions/{analysis['suggestions'][0]['id']}",
        json={"status": "accepted", "editedText": None},
    )
    assert accepted.status_code == 200

    with session_factory() as session:
        claimed = session.scalar(select(Draft).where(Draft.resume_id == resume_id))
        assert claimed is not None
        assert claimed.analysis_id == analysis["id"]
        document = claimed.document

    saved = client.put(
        f"/api/resumes/{resume_id}/draft",
        json={"baseVersionId": base_version_id, "document": document},
    )
    assert saved.status_code == 200

    with session_factory() as session:
        released = session.scalar(select(Draft).where(Draft.resume_id == resume_id))
        assert released is not None
        assert released.analysis_id is None


def test_analysis_without_confirmed_suggestion_has_no_optimized_draft(
    client, resume_factory
) -> None:
    _, base_version_id = resume_factory()
    analysis = _create_completed_analysis(client, base_version_id)

    response = client.post(f"/api/analyses/{analysis['id']}/versions")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_analysis_cannot_reuse_another_analysis_optimized_draft(
    client, resume_factory
) -> None:
    _, base_version_id = resume_factory()
    first = _create_completed_analysis(client, base_version_id)
    accepted = client.patch(
        f"/api/suggestions/{first['suggestions'][0]['id']}",
        json={"status": "accepted", "editedText": None},
    )
    assert accepted.status_code == 200
    second = _create_completed_analysis(client, base_version_id)

    response = client.patch(
        f"/api/suggestions/{second['suggestions'][0]['id']}",
        json={"status": "accepted", "editedText": None},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUGGESTION_STATE_CONFLICT"


def test_old_analysis_cannot_overwrite_newer_version_draft(
    client, resume_factory
) -> None:
    resume_id, base_version_id = resume_factory()
    analysis = _create_completed_analysis(client, base_version_id)
    newer_document = client.get(
        f"/api/resume-versions/{base_version_id}"
    ).json()["data"]["document"]
    newer_document["basicInfo"]["name"] = "新版本草稿"
    newer = client.post(
        f"/api/resumes/{resume_id}/versions",
        json={
            "source": "manual",
            "baseVersionId": base_version_id,
            "document": newer_document,
        },
    ).json()["data"]
    saved_draft = client.put(
        f"/api/resumes/{resume_id}/draft",
        json={"baseVersionId": newer["id"], "document": newer_document},
    )
    assert saved_draft.status_code == 200

    response = client.patch(
        f"/api/suggestions/{analysis['suggestions'][0]['id']}",
        json={"status": "accepted", "editedText": None},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SUGGESTION_STATE_CONFLICT"
    draft = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]
    assert draft["baseVersionId"] == newer["id"]
    assert draft["document"]["basicInfo"]["name"] == "新版本草稿"


def test_processing_analysis_cannot_persist_version(
    client, resume_factory, monkeypatch
) -> None:
    monkeypatch.setattr(service, "run_analysis", lambda *_args, **_kwargs: None)
    _, base_version_id = resume_factory()
    created = client.post(
        "/api/analyses",
        json={"resumeVersionId": base_version_id, "jdText": JD_TEXT},
    )
    analysis_id = created.json()["data"]["id"]

    response = client.post(f"/api/analyses/{analysis_id}/versions")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_IN_PROGRESS"