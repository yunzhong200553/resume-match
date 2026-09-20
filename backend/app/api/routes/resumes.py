"""简历构建相关接口（模块 A）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import DbSession
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.response import envelope
from app.schemas.resume import (
    CreateResumeRequest,
    CreateVersionRequest,
    ParseTextRequest,
    SaveDraftRequest,
)
from app.services import resume_service, version_service
from app.services.parsing.importer import import_resume_bytes
from app.services.parsing.text_parser import parse_resume_text

router = APIRouter()


def _resume_detail(db: Session, resume_id: str) -> dict[str, Any]:
    resume = resume_service.get_resume(db, resume_id)
    draft = resume_service.get_draft(db, resume_id)
    versions = version_service.list_versions(db, resume_id)
    return {
        "resume": resume.to_payload(),
        "draft": draft.to_payload() if draft else None,
        "versions": [version.to_summary() for version in versions],
    }


@router.post("/resumes", status_code=201, summary="创建简历")
def create_resume(payload: CreateResumeRequest, db: DbSession) -> dict[str, Any]:
    resume = resume_service.create_resume(db, title=payload.title, basic_info=payload.basic_info)
    return envelope(_resume_detail(db, resume.id))


@router.get("/resumes", summary="获取历史简历列表")
def list_resumes(db: DbSession) -> dict[str, Any]:
    return envelope({"items": [resume.to_payload() for resume in resume_service.list_resumes(db)]})


@router.post("/resumes/parse-text", summary="拆分用户粘贴的完整文本")
def parse_text(payload: ParseTextRequest) -> dict[str, Any]:
    outcome = parse_resume_text(payload.text)
    return envelope(
        {
            "document": outcome.document.to_storage(),
            "warnings": outcome.warnings,
            "sourceTextLength": outcome.source_text_length,
        }
    )


@router.post("/resumes/import", summary="上传 PDF/DOCX 并返回待确认结构")
async def import_resume(file: UploadFile = File(...)) -> dict[str, Any]:
    # 先用声明的大小拦截超大文件，避免把整个文件读进内存
    declared_size = getattr(file, "size", None)
    if isinstance(declared_size, int) and declared_size > settings.max_upload_bytes:
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            f"文件超过 {settings.max_upload_mb} MB 限制。",
            details={"sizeBytes": declared_size, "maxBytes": settings.max_upload_bytes},
        )

    data = await file.read()
    outcome = import_resume_bytes(
        filename=file.filename or "",
        content_type=file.content_type,
        data=data,
    )
    return envelope(
        {
            "document": outcome.document.to_storage(),
            "warnings": outcome.warnings,
            "source": {
                "filename": outcome.filename,
                "format": outcome.file_format,
                "sizeBytes": outcome.size_bytes,
            },
        }
    )


@router.get("/resumes/{resume_id}", summary="获取简历详情和当前草稿")
def get_resume(resume_id: str, db: DbSession) -> dict[str, Any]:
    return envelope(_resume_detail(db, resume_id))


@router.put("/resumes/{resume_id}/draft", summary="保存草稿和排序")
def save_draft(resume_id: str, payload: SaveDraftRequest, db: DbSession) -> dict[str, Any]:
    draft = resume_service.save_draft(
        db,
        resume_id=resume_id,
        document=payload.document,
        base_version_id=payload.base_version_id,
    )
    return envelope({"draft": draft.to_payload()})


@router.post("/resumes/{resume_id}/versions", status_code=201, summary="从草稿创建不可变版本")
def create_version(
    resume_id: str, payload: CreateVersionRequest, db: DbSession
) -> dict[str, Any]:
    version = version_service.create_version(
        db,
        resume_id=resume_id,
        source=payload.source,
        document=payload.document,
        base_version_id=payload.base_version_id,
    )
    return envelope(version.to_payload())


@router.get("/resumes/{resume_id}/versions", summary="获取历史版本列表")
def list_versions(resume_id: str, db: DbSession) -> dict[str, Any]:
    versions = version_service.list_versions(db, resume_id)
    return envelope({"items": [version.to_summary() for version in versions]})
