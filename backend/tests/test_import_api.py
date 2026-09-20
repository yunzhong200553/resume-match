"""文件导入接口测试：A-01、A-02、A-03、A-04 与类型校验。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.fixtures import write_reference_style_docx, write_scanned_pdf, write_text_pdf

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"


def test_a01_import_text_pdf_returns_editable_structure(
    client: TestClient, tmp_path: Path
) -> None:
    pdf_path = write_text_pdf(tmp_path / "resume.pdf")

    response = client.post(
        "/api/resumes/import",
        files={"file": ("resume.pdf", pdf_path.read_bytes(), PDF_MIME)},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source"] == {
        "filename": "resume.pdf",
        "format": "pdf",
        "sizeBytes": pdf_path.stat().st_size,
    }
    assert data["document"]["basicInfo"]["name"] == "李小明"
    types = [section["type"] for section in data["document"]["sections"]]
    assert types == ["education", "experience", "project", "skill"]
    assert data["document"]["sections"][2]["items"][0]["fields"]["name"] == "ResumeMatch"


def test_a02_import_docx_returns_editable_structure(client: TestClient, tmp_path: Path) -> None:
    docx_path = write_reference_style_docx(tmp_path / "resume.docx")

    response = client.post(
        "/api/resumes/import",
        files={"file": ("resume.docx", docx_path.read_bytes(), DOCX_MIME)},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source"]["format"] == "docx"
    assert data["document"]["basicInfo"] == {
        "name": "李小明",
        "phone": "13800000000",
        "email": "lixiaoming@example.com",
        "location": "杭州",
        "jobTarget": "后端开发工程师",
    }
    experience = data["document"]["sections"][1]["items"][0]
    assert experience["fields"]["company"] == "杭州云帆科技有限公司"
    assert "订单系统重构" in experience["content"]
    skills = data["document"]["sections"][3]["items"]
    assert [item["fields"]["category"] for item in skills] == ["编程", "AI工具", "协作工具"]


def test_a03_scanned_pdf_is_rejected(client: TestClient, tmp_path: Path) -> None:
    pdf_path = write_scanned_pdf(tmp_path / "scanned.pdf")

    response = client.post(
        "/api/resumes/import",
        files={"file": ("scanned.pdf", pdf_path.read_bytes(), PDF_MIME)},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_SCANNED_PDF"
    assert body["error"]["message"] == "未检测到可提取文本，请改用手动录入。"
    assert body["requestId"].startswith("req_")


def test_a04_file_too_large_is_rejected(client: TestClient) -> None:
    oversized = b"%PDF-1.4\n" + b"0" * (settings.max_upload_bytes + 1024)

    response = client.post(
        "/api/resumes/import",
        files={"file": ("big.pdf", oversized, PDF_MIME)},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_unsupported_extension_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/resumes/import",
        files={"file": ("resume.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "FILE_TYPE_NOT_SUPPORTED"


def test_mime_mismatch_is_rejected(client: TestClient, tmp_path: Path) -> None:
    docx_path = write_reference_style_docx(tmp_path / "resume.docx")

    response = client.post(
        "/api/resumes/import",
        files={"file": ("resume.docx", docx_path.read_bytes(), "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "FILE_TYPE_NOT_SUPPORTED"


def test_uploaded_file_is_stored_with_random_name(client: TestClient, tmp_path: Path) -> None:
    docx_path = write_reference_style_docx(tmp_path / "我的简历.docx")

    response = client.post(
        "/api/resumes/import",
        files={"file": ("我的简历.docx", docx_path.read_bytes(), DOCX_MIME)},
    )

    assert response.status_code == 200
    stored = list(settings.upload_dir.glob("*.docx"))
    assert len(stored) == 1
    assert stored[0].name.startswith("upload_")
    assert "简历" not in stored[0].name


def test_parse_text_endpoint_returns_warnings(client: TestClient) -> None:
    response = client.post(
        "/api/resumes/parse-text",
        json={"text": "姓名：测试\n项目经历\n某项目\n- 缺少日期。"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["sourceTextLength"] > 0
    assert isinstance(data["warnings"], list)
    assert data["document"]["sections"][0]["type"] == "project"


def test_parse_text_rejects_blank_input(client: TestClient) -> None:
    response = client.post("/api/resumes/parse-text", json={"text": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
