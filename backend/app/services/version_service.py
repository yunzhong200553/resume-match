"""版本服务：草稿到不可变快照的唯一入口。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.db.models import ResumeVersion
from app.schemas.resume import VersionSource
from app.schemas.resume_document import ResumeDocument
from app.services import resume_service


def create_version(
    db: Session,
    *,
    resume_id: str,
    source: VersionSource,
    document: ResumeDocument | None = None,
    base_version_id: str | None = None,
) -> ResumeVersion:
    """``document`` 为空时取当前草稿内容。

    正式版本一旦写入即不可修改（ORM 层已拦截 UPDATE），
    因此这里是「创建新版本」的唯一入口。
    """

    resume_service.get_resume(db, resume_id)

    if document is None:
        document = resume_service.get_draft_document(db, resume_id)
        if document is None:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "当前没有草稿内容，请在请求中提供 document。",
                details={"resumeId": resume_id},
            )

    if base_version_id is not None:
        parent = get_version(db, base_version_id)
        if parent.resume_id != resume_id:
            raise AppError(
                ErrorCode.VERSION_NOT_FOUND,
                details={"resumeId": resume_id, "versionId": base_version_id},
            )
        parent_id: str | None = parent.id
    else:
        latest = resume_service.latest_version(db, resume_id)
        parent_id = latest.id if latest else None

    latest = resume_service.latest_version(db, resume_id)
    next_number = (latest.version if latest else 0) + 1

    version = ResumeVersion(
        id=new_id("version"),
        resume_id=resume_id,
        version=next_number,
        parent_version_id=parent_id,
        source=source.value,
        document=document.to_storage(),
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def list_versions(db: Session, resume_id: str) -> list[ResumeVersion]:
    resume_service.get_resume(db, resume_id)
    statement = (
        select(ResumeVersion)
        .where(ResumeVersion.resume_id == resume_id)
        .order_by(ResumeVersion.version.asc())
    )
    return list(db.execute(statement).scalars().all())


def get_version(db: Session, version_id: str) -> ResumeVersion:
    version = db.get(ResumeVersion, version_id)
    if version is None:
        raise AppError(ErrorCode.VERSION_NOT_FOUND, details={"versionId": version_id})
    return version


def load_document(version: ResumeVersion) -> ResumeDocument:
    """把快照 JSON 还原为契约对象；历史数据结构非法时明确报错而不是静默降级。"""

    try:
        return ResumeDocument.model_validate(version.document)
    except Exception as exc:  # pragma: no cover - 只在数据被外部篡改时出现
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "版本快照不符合 ResumeDocument 契约。",
            details={"versionId": version.id, "reason": str(exc)},
        ) from exc
