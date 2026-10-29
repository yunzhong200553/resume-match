"""Named layouts, isolated JD edits and layout-specific exports."""

from copy import deepcopy
from io import BytesIO
from urllib.parse import unquote

import fitz
import pytest
from docx import Document

from app.core.config import settings
from app.services.analysis import deepseek
from tests.fixtures import sample_document_dict

JD = "负责 Python 后端接口开发、SQL 数据查询与接口测试，能够根据真实业务需求设计和维护 API，熟悉 FastAPI，有清晰的项目职责表达与团队协作能力。"


def _create_layout(client, resume_id, name, document=None, analysis_id=None):
    response = client.post(f"/api/resumes/{resume_id}/layouts", json={
        "name": name, "jdText": JD, "document": document or sample_document_dict(), "analysisId": analysis_id,
    })
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_multiple_named_layouts_preserve_the_base_and_each_other(client, resume_factory):
    resume_id, _ = resume_factory(create_version=False)
    before = client.get(f"/api/resumes/{resume_id}").json()["data"]
    first_doc = deepcopy(before["draft"]["document"])
    first_doc["sections"][2]["items"][0]["content"] = "BACKEND-LAYOUT"
    first_doc["sections"][3]["hidden"] = True
    first = _create_layout(client, resume_id, "后端工程师", first_doc)
    second_doc = deepcopy(before["draft"]["document"])
    second_doc["sections"].reverse()
    for index, section in enumerate(second_doc["sections"]):
        section["order"] = index
    second = _create_layout(client, resume_id, "产品经理", second_doc)

    listed = client.get(f"/api/resumes/{resume_id}/layouts").json()["data"]["items"]
    assert {layout["name"] for layout in listed} == {"后端工程师", "产品经理"}
    assert all("document" not in layout for layout in listed)
    assert client.get(f"/api/resume-layouts/{first['id']}").json()["data"]["document"] == first_doc
    assert client.get(f"/api/resume-layouts/{second['id']}").json()["data"]["document"] == second_doc
    after = client.get(f"/api/resumes/{resume_id}").json()["data"]
    assert after["draft"] == before["draft"]
    assert after["versions"] == before["versions"] == []


def test_layout_can_be_updated_in_place_and_rejects_stale_saves(client, resume_factory):
    resume_id, _ = resume_factory(create_version=False)
    layout = _create_layout(client, resume_id, "后端岗位")
    payload = {key: layout[key] for key in ("name", "jdText", "document", "analysisId")}
    payload["name"] = "后端岗位｜某公司"
    payload["document"]["sections"][2]["items"][0]["content"] = "UPDATED-LAYOUT"
    payload["expectedUpdatedAt"] = layout["updatedAt"]
    updated = client.put(f"/api/resume-layouts/{layout['id']}", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["id"] == layout["id"]
    assert client.put(f"/api/resume-layouts/{layout['id']}", json=payload).status_code == 409
    assert len(client.get(f"/api/resumes/{resume_id}/layouts").json()["data"]["items"]) == 1
    assert client.get(f"/api/resumes/{resume_id}").json()["data"]["versions"] == []


def test_duplicate_layout_names_are_not_silently_overwritten(client, resume_factory):
    resume_id, _ = resume_factory()
    first = _create_layout(client, resume_id, "产品经理")
    duplicate = client.post(f"/api/resumes/{resume_id}/layouts", json={
        "name": "产品经理", "document": sample_document_dict(),
    })
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "LAYOUT_NAME_CONFLICT"
    second = _create_layout(client, resume_id, "后端开发")
    renamed = client.put(f"/api/resume-layouts/{second['id']}", json={
        "name": first["name"], "document": second["document"], "expectedUpdatedAt": second["updatedAt"],
    })
    assert renamed.status_code == 409
    assert renamed.json()["error"]["code"] == "LAYOUT_NAME_CONFLICT"


@pytest.mark.parametrize("name", ["", "  ", "岗" * 101])
def test_layout_name_is_validated(client, resume_factory, name):
    resume_id, _ = resume_factory()
    response = client.post(f"/api/resumes/{resume_id}/layouts", json={"name": name, "document": sample_document_dict()})
    assert response.status_code == 422


def test_layouts_are_scoped_to_the_selected_resume(client, resume_factory):
    first, _ = resume_factory(title="第一份资料")
    second, _ = resume_factory(title="第二份资料")
    layout = _create_layout(client, first, "后端岗位")
    assert client.get(f"/api/resumes/{second}/layouts").json()["data"]["items"] == []
    assert client.get("/api/resume-layouts/layout_missing").status_code == 404
    analysis_id = client.post("/api/analyses", json={
        "resumeVersionId": client.get(f"/api/resumes/{first}").json()["data"]["versions"][0]["id"], "jdText": JD,
    }).json()["data"]["id"]
    invalid = client.post(f"/api/resumes/{second}/layouts", json={
        "name": layout["name"], "document": layout["document"], "analysisId": analysis_id,
    })
    assert invalid.status_code == 422


@pytest.mark.parametrize("file_format", ["docx", "pdf"])
def test_exports_use_the_selected_saved_layout_and_job_name(client, resume_factory, file_format):
    resume_id, _ = resume_factory(create_version=False)
    base = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]["document"]
    layout_document = deepcopy(base)
    layout_document["sections"][2]["items"][0]["fields"]["name"] = "TARGET-LAYOUT"
    layout_document["sections"][2]["items"][0]["content"] = "TARGET-CONTENT"
    layout_document["sections"][3]["hidden"] = True
    layout = _create_layout(client, resume_id, "后端工程师", layout_document)
    base["sections"][2]["items"][0]["content"] = "NEW-BASE-CONTENT"
    client.put(f"/api/resumes/{resume_id}/draft", json={"document": base})

    exported = client.post(f"/api/resume-layouts/{layout['id']}/exports", json={
        "templateId": "classic_single_column", "format": file_format,
    })
    assert exported.status_code == 201, exported.text
    downloaded = client.get(exported.json()["data"]["downloadUrl"])
    assert downloaded.status_code == 200
    assert "后端工程师" in unquote(downloaded.headers["content-disposition"])
    if file_format == "docx":
        text = "\n".join(paragraph.text for paragraph in Document(BytesIO(downloaded.content)).paragraphs)
    else:
        with fitz.open(stream=downloaded.content, filetype="pdf") as pdf:
            text = "".join(pdf.load_page(index).get_text() for index in range(pdf.page_count))
    assert "TARGET-LAYOUT" in text and "TARGET-CONTENT" in text
    assert "NEW-BASE-CONTENT" not in text
    assert "腾讯文档" not in text
    assert client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]["document"] == base


def test_ai_confirm_changes_only_the_jd_copy_until_layout_save(client, resume_factory, monkeypatch):
    resume_id, version_id = resume_factory()
    original = client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"]
    analysis_id = client.post("/api/analyses", json={"resumeVersionId": version_id, "jdText": JD}).json()["data"]["id"]
    suggestion = client.get(f"/api/analyses/{analysis_id}").json()["data"]["suggestions"][0]
    workspace = deepcopy(original["document"])
    item = workspace["sections"][1]["items"][0]
    item["content"] = "当前排版中人工调整过的内容。"
    item["fields"]["role"] = "当前排版角色"
    seen = []

    def rewrite(**kwargs):
        seen.append(kwargs)
        return deepseek.RewriteResult(rewritten="AI 优化后的当前排版内容。", explanation="仅改进已有表达。")

    monkeypatch.setattr(settings, "analysis_provider", "deepseek")
    monkeypatch.setattr(deepseek, "rewrite_content", rewrite)
    proposal = client.post(f"/api/suggestions/{suggestion['id']}/rewrite", json={
        "currentContent": item["content"], "document": workspace,
    })
    assert proposal.status_code == 200, proposal.text
    assert seen[0]["fields"]["role"] == "当前排版角色"
    confirmed = client.post(f"/api/suggestions/{suggestion['id']}/preview-confirm", json={
        "original": item["content"], "replacement": proposal.json()["data"]["rewritten"], "document": workspace,
    })
    assert confirmed.status_code == 200, confirmed.text
    saved_doc = confirmed.json()["data"]["document"]
    assert saved_doc["sections"][1]["items"][0]["content"] == "AI 优化后的当前排版内容。"
    assert client.get(f"/api/resumes/{resume_id}").json()["data"]["draft"] == original
    layout = _create_layout(client, resume_id, "AI 排版", saved_doc, analysis_id)
    assert layout["document"] == saved_doc
    repeated = client.post(f"/api/suggestions/{suggestion['id']}/preview-confirm", json={
        "original": item["content"], "replacement": "再次替换", "document": workspace,
    })
    assert repeated.status_code == 409


def test_deleting_resume_cascades_named_layouts(client, resume_factory, db_engine):
    with db_engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    resume_id, _ = resume_factory()
    layout = _create_layout(client, resume_id, "待删除排版")
    assert client.delete(f"/api/resumes/{resume_id}").status_code == 204
    assert client.get(f"/api/resume-layouts/{layout['id']}").status_code == 404
