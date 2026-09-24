"""JD 分析任务的持久化服务。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.db.models import Analysis as AnalysisRecord
from app.schemas.analysis import (
    Analysis,
    AnalysisStatus,
    CreateAnalysisResult,
    ProviderState,
    ProviderStates,
    ProviderStatus,
    Suggestion,
)
from app.services import version_service

JD_TEXT_MIN_LENGTH = 50
JD_TEXT_MAX_LENGTH = 20_000


def create_analysis(
    db: Session, *, resume_version_id: str, jd_text: str
) -> AnalysisRecord:
    version_service.get_version(db, resume_version_id)
    if len(jd_text) < JD_TEXT_MIN_LENGTH:
        raise AppError(ErrorCode.JD_TEXT_TOO_SHORT)
    if len(jd_text) > JD_TEXT_MAX_LENGTH:
        raise AppError(ErrorCode.JD_TEXT_TOO_LONG)

    providers = _queued_providers().model_dump(by_alias=True, mode="json")
    analysis = AnalysisRecord(
        id=new_id("analysis"),
        resume_version_id=resume_version_id,
        jd_text=jd_text,
        status=AnalysisStatus.PROCESSING.value,
        overall_score=None,
        score_level=None,
        summary=None,
        score_breakdown=[],
        item_matches=[],
        missing_requirements=[],
        provider_states=providers,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def get_analysis(db: Session, analysis_id: str) -> AnalysisRecord:
    analysis = db.get(AnalysisRecord, analysis_id)
    if analysis is None:
        raise AppError(ErrorCode.ANALYSIS_NOT_FOUND, details={"analysisId": analysis_id})
    return analysis


def create_payload(analysis: AnalysisRecord) -> dict[str, object]:
    payload = CreateAnalysisResult(
        id=analysis.id,
        resume_version_id=analysis.resume_version_id,
        status=AnalysisStatus(analysis.status),
        providers=ProviderStates.model_validate(analysis.provider_states),
        created_at=analysis.created_at,
    )
    return payload.model_dump(by_alias=True, mode="json")


def analysis_payload(analysis: AnalysisRecord) -> dict[str, object]:
    payload = Analysis(
        id=analysis.id,
        resume_version_id=analysis.resume_version_id,
        status=AnalysisStatus(analysis.status),
        jd_text=analysis.jd_text,
        overall_score=analysis.overall_score,
        score_level=analysis.score_level,
        summary=analysis.summary,
        score_breakdown=analysis.score_breakdown,
        item_matches=analysis.item_matches,
        missing_requirements=analysis.missing_requirements,
        suggestions=[
            Suggestion(
                id=item.id,
                analysis_id=item.analysis_id,
                section_id=item.section_id,
                item_id=item.item_id,
                target_field="content",
                original=item.original,
                suggested=item.suggested,
                reason=item.reason,
                status=item.status,
                edited_text=item.edited_text,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in analysis.suggestions
        ],
        providers=ProviderStates.model_validate(analysis.provider_states),
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        completed_at=analysis.completed_at,
    )
    return payload.model_dump(by_alias=True, mode="json")


def _queued_providers() -> ProviderStates:
    queued = ProviderState(status=ProviderStatus.QUEUED, attempts=0)
    return ProviderStates(score_agent=queued, suggestion_agent=queued.model_copy())