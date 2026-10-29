"""导出编排：读取不可变版本 -> 渲染 DOCX -> 可选转换为 PDF -> 记录结果。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.db.models import ExportRecord, utcnow
from app.schemas.export import ExportFormat, ExportStatus
from app.schemas.resume_document import ResumeDocument
from app.services import version_service
from app.services.export import libreoffice, templates
from app.services.export.pdf_renderer import render_pdf
from app.services.export.renderer import render_resume

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def create_export(
    db: Session,
    *,
    version_id: str,
    template_id: str,
    export_format: ExportFormat,
    layout_id: str | None = None,
) -> ExportRecord:
    version = version_service.get_version(db, version_id)
    spec = templates.get_template(template_id)
    templates.template_path(spec)

    record = ExportRecord(
        id=new_id("export"),
        resume_version_id=version.id,
        template_id=spec.id,
        format=export_format.value,
        status=ExportStatus.PROCESSING.value,
        layout_id=layout_id,
    )
    db.add(record)
    db.commit()

    settings.ensure_dirs()
    try:
        document = version_service.load_document(version)
        final_path = render_document(
            document=document,
            template_id=template_id,
            output_dir=settings.export_dir,
            basename=record.id,
            export_format=export_format,
            resume_title=version.resume.title if version.resume else "",
        )
    except AppError as error:
        _mark_failed(db, record, error)
        raise
    except Exception as error:  # pragma: no cover - 渲染器未预期异常
        wrapped = AppError(ErrorCode.EXPORT_FAILED, details={"reason": str(error)})
        _mark_failed(db, record, wrapped)
        raise wrapped from error

    record.status = ExportStatus.COMPLETED.value
    record.file_path = str(final_path)
    record.completed_at = utcnow()
    db.commit()
    db.refresh(record)
    return record


def render_document(
    *, document: ResumeDocument, template_id: str, output_dir: Path,
    basename: str, export_format: ExportFormat, resume_title: str = "",
) -> Path:
    spec = templates.get_template(template_id)
    document = document.for_output()
    docx_path = output_dir / f"{basename}.docx"
    render_resume(
        document, template_path=templates.template_path(spec),
        output_path=docx_path, template=spec, resume_title=resume_title,
    )
    if export_format is ExportFormat.DOCX:
        return docx_path
    if libreoffice.is_available():
        return libreoffice.convert_to_pdf(docx_path, output_dir)
    return render_pdf(document, output_path=output_dir / f"{basename}.pdf")


def export_payload(record: ExportRecord) -> dict[str, Any]:
    """组装对外响应体；只有完成的导出才带 downloadUrl。"""

    url = (
        download_url(record.id)
        if record.status == ExportStatus.COMPLETED.value and record.file_path
        else None
    )
    return record.to_payload(download_url=url)


def get_export(db: Session, export_id: str) -> ExportRecord:
    record = db.get(ExportRecord, export_id)
    if record is None:
        raise AppError(ErrorCode.EXPORT_NOT_FOUND, details={"exportId": export_id})
    return record


def download_path(db: Session, export_id: str) -> tuple[Path, str]:
    """返回产物路径与媒体类型；客户端只能通过 ExportRecord 授权下载。"""

    record = get_export(db, export_id)
    if record.status != ExportStatus.COMPLETED.value or not record.file_path:
        raise AppError(
            ErrorCode.EXPORT_FAILED,
            "导出尚未完成，无法下载。",
            details={"exportId": export_id, "status": record.status},
        )
    path = Path(record.file_path)
    if not path.exists():
        raise AppError(
            ErrorCode.EXPORT_FAILED,
            "导出文件已不存在，请重新导出。",
            details={"exportId": export_id},
        )
    return path, MEDIA_TYPES.get(record.format, "application/octet-stream")


def download_url(export_id: str) -> str:
    return f"/api/exports/{export_id}/download"


def _mark_failed(db: Session, record: ExportRecord, error: AppError) -> None:
    record.status = ExportStatus.FAILED.value
    record.error_code = error.code.value
    record.error_message = error.message
    record.completed_at = utcnow()
    db.commit()
