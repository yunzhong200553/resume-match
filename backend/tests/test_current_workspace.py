"""可重复保存、可恢复隐藏及真实分页预览回归。"""

from io import BytesIO

import fitz
from docx import Document

from tests.fixtures import sample_document_dict


def test_repeated_saves_update_one_document_without_creating_versions(client, resume_factory):
    resume_id, _ = resume_factory(create_version=False)
    document = sample_document_dict()
    for name in ["第一次修改", "第二次修改", "最后修改"]:
        document["basicInfo"]["name"] = name
        response = client.put(f"/api/resumes/{resume_id}/draft", json={"document": document})
        assert response.status_code == 200
    detail = client.get(f"/api/resumes/{resume_id}").json()["data"]
    assert detail["draft"]["document"]["basicInfo"]["name"] == "最后修改"
    assert detail["versions"] == []
    first = client.post(f"/api/resumes/{resume_id}/snapshot").json()["data"]
    second = client.post(f"/api/resumes/{resume_id}/snapshot").json()["data"]
    assert first["id"] == second["id"]
    assert len(client.get(f"/api/resumes/{resume_id}").json()["data"]["versions"]) == 1


def test_hidden_sections_and_items_are_recoverable_but_not_exported(client, resume_factory):
    document = sample_document_dict()
    document["sections"][0]["hidden"] = True
    document["sections"][2]["items"][0]["hidden"] = True
    document["sections"][2]["items"][0]["content"] = "HIDDEN-PROJECT-CONTENT"
    resume_id, version_id = resume_factory(document)
    detail = client.get(f"/api/resumes/{resume_id}").json()["data"]
    assert detail["draft"]["document"]["sections"][2]["items"][0]["content"] == "HIDDEN-PROJECT-CONTENT"
    exported = client.post(f"/api/resume-versions/{version_id}/exports", json={"templateId": "classic_single_column", "format": "docx"}).json()["data"]
    file = client.get(exported["downloadUrl"])
    text = "\n".join(paragraph.text for paragraph in Document(BytesIO(file.content)).paragraphs)
    assert "HIDDEN-PROJECT-CONTENT" not in text
    assert "浙江大学" not in text
    assert "杭州云帆科技有限公司" in text
    document["sections"][0]["hidden"] = False
    document["sections"][2]["items"][0]["hidden"] = False
    restored = client.put(f"/api/resumes/{resume_id}/draft", json={"document": document})
    assert restored.status_code == 200
    assert not restored.json()["data"]["draft"]["document"]["sections"][2]["items"][0]["hidden"]


def test_preview_page_count_matches_actual_pdf_export(client, resume_factory):
    document = sample_document_dict()
    document["sections"][2]["items"][0]["content"] = "\n".join(f"ROW-{index}: API development and testing with existing evidence." for index in range(110))
    resume_id, version_id = resume_factory(document)
    before = client.get(f"/api/resumes/{resume_id}").json()["data"]
    preview = client.post("/api/resume-preview", json={"document": document, "templateId": "classic_single_column"})
    assert preview.status_code == 200, preview.text
    pages = preview.json()["data"]
    assert pages["pageCount"] >= 2
    assert [page["pageNumber"] for page in pages["pages"]] == list(range(1, pages["pageCount"] + 1))
    assert all(page["image"].startswith("data:image/png;base64,") for page in pages["pages"])
    exported = client.post(f"/api/resume-versions/{version_id}/exports", json={"templateId": "classic_single_column", "format": "pdf"}).json()["data"]
    with fitz.open(stream=client.get(exported["downloadUrl"]).content, filetype="pdf") as pdf:
        assert pdf.page_count == pages["pageCount"]
        assert "ROW-109" in "".join(page.get_text() for page in pdf)
    after = client.get(f"/api/resumes/{resume_id}").json()["data"]
    assert after["draft"] == before["draft"]
    assert len(after["versions"]) == len(before["versions"])
