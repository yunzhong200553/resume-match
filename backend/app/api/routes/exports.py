"""共享导出服务接口，模块 A 与模块 B 使用同一组端点。"""

from __future__ import annotations

from typing import Any
import base64
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.deps import DbSession
from app.core.response import envelope
from app.schemas.export import ExportFormat, ExportRequest, PreviewRequest
from app.services import version_service
from app.services.export import export_service
from app.services.export.templates import TEMPLATE_FORMATS, list_templates

router = APIRouter()


@router.post("/resume-preview", summary="按真实 PDF 渲染流程生成分页预览（不保存简历）")
def preview_resume(payload: PreviewRequest) -> dict[str, Any]:
    with TemporaryDirectory(prefix="resume-preview-") as directory:
        pdf_path = export_service.render_document(
            document=payload.document, template_id=payload.template_id,
            output_dir=Path(directory), basename="preview", export_format=ExportFormat.PDF,
        )
        with fitz.open(pdf_path) as pdf:
            pages = []
            for index in range(pdf.page_count):
                page = pdf.load_page(index)
                pages.append({
                    "pageNumber": index + 1,
                    "image": "data:image/png;base64," + base64.b64encode(page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).tobytes("png")).decode("ascii"),
                    "width": page.rect.width,
                    "height": page.rect.height,
                })
    return envelope({"pageCount": len(pages), "pages": pages})


@router.get("/export-templates", summary="获取可用导出模板")
def list_export_templates() -> dict[str, Any]:
    items = [
        {
            "id": spec.id,
            "name": spec.name,
            "description": spec.description,
            "formats": list(TEMPLATE_FORMATS),
        }
        for spec in list_templates()
    ]
    return envelope({"items": items})


@router.post(
    "/resume-versions/{version_id}/exports",
    status_code=201,
    summary="创建 DOCX/PDF 导出任务",
)
def create_export(version_id: str, payload: ExportRequest, db: DbSession) -> dict[str, Any]:
    record = export_service.create_export(
        db,
        version_id=version_id,
        template_id=payload.template_id,
        export_format=payload.format,
    )
    return envelope(export_service.export_payload(record))


@router.get("/exports/{export_id}", summary="获取导出状态")
def get_export(export_id: str, db: DbSession) -> dict[str, Any]:
    record = export_service.get_export(db, export_id)
    return envelope(export_service.export_payload(record))


@router.get("/exports/{export_id}/download", summary="下载生成文件")
def download_export(export_id: str, db: DbSession) -> FileResponse:
    record = export_service.get_export(db, export_id)
    path, media_type = export_service.download_path(db, export_id)

    version = version_service.get_version(db, record.resume_version_id)
    title = version.resume.title if version.resume else "resume"
    if record.layout is not None:
        title = f"{title}-{record.layout.name}"
    filename = f"{title}.{record.format}"

    return FileResponse(path, media_type=media_type, filename=filename)
