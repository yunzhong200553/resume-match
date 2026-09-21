"""简历主体与草稿服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.db.models import Draft, Resume, ResumeVersion, utcnow
from app.schemas.resume_document import BasicInfo, ResumeDocument, normalize_orders


def create_resume(db: Session, *, title: str, basic_info: BasicInfo | None = None) -> Resume:
    resume = Resume(id=new_id("resume"), title=title.strip())
    document = ResumeDocument(basic_info=basic_info or BasicInfo(), sections=[])
    draft = Draft(
        id=new_id("draft"),
        resume_id=resume.id,
        base_version_id=None,
        document=document.to_storage(),
    )
    db.add_all([resume, draft])
    db.commit()
    db.refresh(resume)
    return resume


def list_resumes(db: Session) -> list[Resume]:
    statement = select(Resume).order_by(Resume.updated_at.desc())
    return list(db.execute(statement).scalars().all())


def get_resume(db: Session, resume_id: str) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise AppError(ErrorCode.RESUME_NOT_FOUND, details={"resumeId": resume_id})
    return resume


def get_draft(db: Session, resume_id: str) -> Draft | None:
    statement = select(Draft).where(Draft.resume_id == resume_id)
    return db.execute(statement).scalar_one_or_none()


def get_draft_document(db: Session, resume_id: str) -> ResumeDocument | None:
    draft = get_draft(db, resume_id)
    if draft is None:
        return None
    return ResumeDocument.model_validate(draft.document)


def save_draft(
    db: Session,
    *,
    resume_id: str,
    document: ResumeDocument,
    base_version_id: str | None = None,
) -> Draft:
    """把校正后的内容写入草稿；草稿可变，正式版本不受影响。"""

    resume = get_resume(db, resume_id)
    if base_version_id is not None:
        _assert_version_belongs_to_resume(db, resume_id, base_version_id)

    normalized = normalize_orders(document)
    draft = get_draft(db, resume_id)
    if draft is None:
        draft = Draft(
            id=new_id("draft"),
            resume_id=resume_id,
            base_version_id=base_version_id,
            document=normalized.to_storage(),
        )
        db.add(draft)
    else:
        draft.document = normalized.to_storage()
        draft.base_version_id = base_version_id
    resume.updated_at = utcnow()  # 让简历列表按最近编辑排序
    db.commit()
    db.refresh(draft)
    return draft


def latest_version(db: Session, resume_id: str) -> ResumeVersion | None:
    statement = (
        select(ResumeVersion)
        .where(ResumeVersion.resume_id == resume_id)
        .order_by(ResumeVersion.version.desc())
        .limit(1)
    )
    return db.execute(statement).scalar_one_or_none()


def _assert_version_belongs_to_resume(
    db: Session, resume_id: str, version_id: str
) -> ResumeVersion:
    version = db.get(ResumeVersion, version_id)
    if version is None or version.resume_id != resume_id:
        raise AppError(
            ErrorCode.VERSION_NOT_FOUND,
            details={"resumeId": resume_id, "versionId": version_id},
        )
    return version
