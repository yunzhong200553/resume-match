"""共享导出服务接口，模块 A 与模块 B 使用同一组端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.deps import DbSession
from app.core.response import envelope
from app.schemas.export import ExportRequest
from app.services import version_service
from app.services.export import export_service
from app.services.export.templates import TEMPLATE_FORMATS, list_templates

router = APIRouter()


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

    filename = f"{record.id}.{record.format}"
    try:
        version = version_service.get_version(db, record.resume_version_id)
        title = version.resume.title if version.resume else "resume"
        filename = f"{title}-v{version.version}.{record.format}"
    except Exception:  # pragma: no cover - 文件名只是锦上添花
        pass

    return FileResponse(path, media_type=media_type, filename=filename)
