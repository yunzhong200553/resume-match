"""Named layouts preserve a separate document without overwriting the base draft."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.db.models import ResumeLayout, utcnow
from app.schemas.layout import SaveLayoutRequest
from app.schemas.resume_document import normalize_orders
from app.services import resume_service, version_service
from app.services.analysis import service as analysis_service


def list_layouts(db: Session, resume_id: str) -> list[ResumeLayout]:
    resume_service.get_resume(db, resume_id)
    return list(db.scalars(select(ResumeLayout).where(ResumeLayout.resume_id == resume_id).order_by(ResumeLayout.updated_at.desc())))


def get_layout(db: Session, layout_id: str) -> ResumeLayout:
    layout = db.get(ResumeLayout, layout_id)
    if layout is None:
        raise AppError(ErrorCode.LAYOUT_NOT_FOUND)
    return layout


def save_layout(
    db: Session, resume_id: str, payload: SaveLayoutRequest, *,
    layout_id: str | None = None, expected_updated_at: datetime | None = None,
) -> ResumeLayout:
    resume = resume_service.get_resume(db, resume_id)
    if payload.analysis_id:
        analysis = analysis_service.get_analysis(db, payload.analysis_id)
        if version_service.get_version(db, analysis.resume_version_id).resume_id != resume_id:
            raise AppError(ErrorCode.VALIDATION_ERROR, "该分析不属于当前简历。")
    values = {
        "name": payload.name, "jd_text": payload.jd_text,
        "document": normalize_orders(payload.document).to_storage(),
        "analysis_id": payload.analysis_id, "updated_at": utcnow(),
    }
    try:
        if layout_id is None:
            layout = ResumeLayout(id=new_id("layout"), resume_id=resume_id, **values)
            db.add(layout)
        else:
            layout = get_layout(db, layout_id)
            if layout.resume_id != resume_id:
                raise AppError(ErrorCode.LAYOUT_NOT_FOUND)
            if expected_updated_at is None:
                raise AppError(ErrorCode.VALIDATION_ERROR, "更新排版需要最后保存时间。")
            expected = expected_updated_at.replace(tzinfo=timezone.utc) if expected_updated_at.tzinfo is None else expected_updated_at
            result = db.execute(
                update(ResumeLayout)
                .where(ResumeLayout.id == layout_id, ResumeLayout.updated_at == expected.astimezone(timezone.utc).replace(tzinfo=None))
                .values(**values).returning(ResumeLayout.id)
                .execution_options(synchronize_session=False)
            )
            if result.scalar_one_or_none() is None:
                db.rollback()
                raise AppError(ErrorCode.LAYOUT_STATE_CONFLICT)
        resume.updated_at = utcnow()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if db.scalar(select(ResumeLayout.id).where(ResumeLayout.resume_id == resume_id, ResumeLayout.name == payload.name)) is not None:
            raise AppError(ErrorCode.LAYOUT_NAME_CONFLICT) from exc
        raise
    db.refresh(layout)
    return layout
