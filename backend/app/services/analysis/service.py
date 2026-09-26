"""JD 分析任务的持久化服务。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.db.models import Analysis as AnalysisRecord
from app.db.models import Suggestion as SuggestionRecord
from app.db.models import utcnow
from app.schemas.analysis import (
    Analysis,
    AnalysisStatus,
    CreateAnalysisResult,
    ProviderState,
    ProviderStates,
    ProviderStatus,
    ScoreProviderResult,
    Suggestion,
    SuggestionProviderResult,
    SuggestionStatus,
)
from app.services import version_service
from app.services.analysis.provider import AnalysisProvider, get_providers

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


def run_analysis(
    db: Session,
    analysis_id: str,
    providers: tuple[AnalysisProvider, AnalysisProvider] | None = None,
) -> AnalysisRecord:
    analysis = get_analysis(db, analysis_id)
    version = version_service.get_version(db, analysis.resume_version_id)
    document = version_service.load_document(version)
    provider_pair = providers or get_providers()
    provider_by_name = {provider.name: provider for provider in provider_pair}
    if set(provider_by_name) != {"scoreAgent", "suggestionAgent"}:
        raise AppError(
            ErrorCode.ANALYSIS_PROVIDER_ERROR,
            "必须同时配置 scoreAgent 和 suggestionAgent。",
        )

    states = ProviderStates.model_validate(analysis.provider_states)
    for state in (states.score_agent, states.suggestion_agent):
        state.status = ProviderStatus.RUNNING
        state.attempts += 1
        state.error_code = None
        state.error_message = None
    analysis.provider_states = states.model_dump(by_alias=True, mode="json")
    db.commit()

    document_payload = document.to_storage()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            name: executor.submit(
                provider.analyze,
                document=document_payload,
                jd_text=analysis.jd_text,
            )
            for name, provider in provider_by_name.items()
        }
        outcomes: dict[str, tuple[dict[str, Any] | None, Exception | None]] = {}
        for name, future in futures.items():
            try:
                outcomes[name] = (future.result(), None)
            except Exception as exc:
                outcomes[name] = (None, exc)

    succeeded = 0
    score_payload, score_error = outcomes["scoreAgent"]
    try:
        if score_error is not None:
            raise score_error
        score_result = ScoreProviderResult.model_validate(score_payload)
        _validate_score_references(score_result, document_payload)
        analysis.overall_score = score_result.overall_score
        analysis.score_level = score_result.score_level.value
        analysis.summary = score_result.summary
        analysis.score_breakdown = [
            item.model_dump(by_alias=True, mode="json")
            for item in score_result.score_breakdown
        ]
        analysis.item_matches = [
            item.model_dump(by_alias=True, mode="json") for item in score_result.item_matches
        ]
        analysis.missing_requirements = [
            item.model_dump(by_alias=True, mode="json")
            for item in score_result.missing_requirements
        ]
        _mark_succeeded(states.score_agent)
        succeeded += 1
    except Exception as exc:
        _mark_failed(states.score_agent, exc)

    suggestion_payload, suggestion_error = outcomes["suggestionAgent"]
    try:
        if suggestion_error is not None:
            raise suggestion_error
        suggestion_result = SuggestionProviderResult.model_validate(suggestion_payload)
        _validate_suggestions(suggestion_result, document_payload)
        for item in suggestion_result.suggestions:
            db.add(
                SuggestionRecord(
                    id=new_id("suggestion"),
                    analysis_id=analysis.id,
                    section_id=item.section_id,
                    item_id=item.item_id,
                    target_field=item.target_field,
                    original=item.original,
                    suggested=item.suggested,
                    reason=item.reason,
                    status=SuggestionStatus.PENDING.value,
                    edited_text=None,
                )
            )
        _mark_succeeded(states.suggestion_agent)
        succeeded += 1
    except Exception as exc:
        _mark_failed(states.suggestion_agent, exc)

    analysis.status = (
        AnalysisStatus.COMPLETED.value
        if succeeded == 2
        else AnalysisStatus.PARTIAL_FAILED.value
        if succeeded == 1
        else AnalysisStatus.FAILED.value
    )
    analysis.provider_states = states.model_dump(by_alias=True, mode="json")
    analysis.completed_at = utcnow()
    db.commit()
    db.refresh(analysis)
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


def _document_items(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (section.get("id", ""), item.get("id", "")): item
        for section in document.get("sections", [])
        for item in section.get("items", [])
    }


def _validate_score_references(
    result: ScoreProviderResult, document: dict[str, Any]
) -> None:
    items = _document_items(document)
    for match in result.item_matches:
        if (match.section_id, match.item_id) not in items:
            raise ValueError("itemMatches 引用了不存在或归属错误的条目")
    requirements = [item.requirement for item in result.missing_requirements]
    if len(requirements) != len(set(requirements)):
        raise ValueError("missingRequirements 不得重复")


def _validate_suggestions(
    result: SuggestionProviderResult, document: dict[str, Any]
) -> None:
    items = _document_items(document)
    targets: set[tuple[str, str, str]] = set()
    for suggestion in result.suggestions:
        key = (suggestion.section_id, suggestion.item_id)
        item = items.get(key)
        if item is None:
            raise ValueError("suggestions 引用了不存在或归属错误的条目")
        if suggestion.original != item.get("content", ""):
            raise ValueError("Suggestion.original 与原始 item.content 不一致")
        target = (*key, suggestion.target_field)
        if target in targets:
            raise ValueError("同一条目和字段不得包含重复建议")
        targets.add(target)


def _mark_succeeded(state: ProviderState) -> None:
    state.status = ProviderStatus.SUCCEEDED
    state.error_code = None
    state.error_message = None


def _mark_failed(state: ProviderState, exc: Exception) -> None:
    state.status = ProviderStatus.FAILED
    state.error_code = (
        "PROVIDER_TIMEOUT"
        if isinstance(exc, TimeoutError)
        or isinstance(exc, AppError) and exc.code is ErrorCode.ANALYSIS_TIMEOUT
        else "INVALID_PROVIDER_RESPONSE"
    )
    state.error_message = (
        "分析服务调用超时。"
        if state.error_code == "PROVIDER_TIMEOUT"
        else "分析服务返回了无效结果。"
    )