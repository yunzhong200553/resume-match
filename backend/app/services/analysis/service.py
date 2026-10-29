"""JD 分析任务的持久化服务。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.db.models import Analysis as AnalysisRecord
from app.db.models import Draft, Resume, ResumeVersion
from app.db.models import Suggestion as SuggestionRecord
from app.db.models import utcnow
from app.schemas.analysis import (
    Analysis,
    AnalysisStatus,
    CreateAnalysisResult,
    ProviderState,
    ProviderStates,
    ProviderStatus,
    RetryAnalysisResult,
    RetryTarget,
    ScoreProviderResult,
    Suggestion,
    SuggestionProviderResult,
    SuggestionStatus,
    UpdateSuggestionResult,
    UpdateSuggestionStatus,
)
from app.schemas.resume import VersionSource
from app.schemas.resume_document import ResumeDocument
from app.services import version_service
from app.services.analysis.provider import AnalysisProvider, get_providers

JD_TEXT_MIN_LENGTH = 50
JD_TEXT_MAX_LENGTH = 20_000


def run_analysis_task(
    bind: Engine | Connection,
    analysis_id: str,
    targets: list[RetryTarget] | None = None,
) -> None:
    with Session(bind=bind) as task_db:
        run_analysis(task_db, analysis_id, targets=targets)


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


def latest_analysis(db: Session, resume_id: str) -> AnalysisRecord | None:
    return db.execute(
        select(AnalysisRecord).join(ResumeVersion, AnalysisRecord.resume_version_id == ResumeVersion.id)
        .where(ResumeVersion.resume_id == resume_id)
        .order_by(AnalysisRecord.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def run_analysis(
    db: Session,
    analysis_id: str,
    providers: tuple[AnalysisProvider, AnalysisProvider] | None = None,
    targets: list[RetryTarget] | None = None,
) -> AnalysisRecord:
    analysis = get_analysis(db, analysis_id)
    version = version_service.get_version(db, analysis.resume_version_id)
    document = version_service.load_document(version)
    target_names: list[RetryTarget] = targets or ["scoreAgent", "suggestionAgent"]

    states = ProviderStates.model_validate(analysis.provider_states)
    for name in target_names:
        state = _provider_state(states, name)
        state.status = ProviderStatus.RUNNING
        state.attempts += 1
        state.error_code = None
        state.error_message = None
    analysis.provider_states = states.model_dump(by_alias=True, mode="json")
    db.commit()

    try:
        provider_pair = providers or get_providers()
        provider_by_name = {provider.name: provider for provider in provider_pair}
        if set(provider_by_name) != {"scoreAgent", "suggestionAgent"}:
            raise AppError(
                ErrorCode.ANALYSIS_PROVIDER_ERROR,
                "必须同时配置 scoreAgent 和 suggestionAgent。",
            )
    except Exception as exc:
        for name in target_names:
            _mark_failed(_provider_state(states, name), exc)
        return _finalize_analysis(db, analysis, states)

    document_payload = document.to_storage()
    provider_document = _provider_document(document.for_output().to_storage())
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            name: executor.submit(
                provider_by_name[name].analyze,
                document=deepcopy(provider_document),
                jd_text=analysis.jd_text,
            )
            for name in target_names
        }
        outcomes: dict[str, tuple[dict[str, Any] | None, Exception | None]] = {}
        for name, future in futures.items():
            try:
                outcomes[name] = (future.result(), None)
            except Exception as exc:
                outcomes[name] = (None, exc)

    if "scoreAgent" in target_names:
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
                item.model_dump(by_alias=True, mode="json")
                for item in score_result.item_matches
            ]
            analysis.missing_requirements = [
                item.model_dump(by_alias=True, mode="json")
                for item in score_result.missing_requirements
            ]
            _mark_succeeded(states.score_agent)
        except Exception as exc:
            _mark_failed(states.score_agent, exc)

    if "suggestionAgent" in target_names:
        suggestion_payload, suggestion_error = outcomes["suggestionAgent"]
        try:
            if suggestion_error is not None:
                raise suggestion_error
            suggestion_result = SuggestionProviderResult.model_validate(suggestion_payload)
            _validate_suggestions(suggestion_result, document_payload)
            _store_new_suggestions(db, analysis.id, suggestion_result)
            _mark_succeeded(states.suggestion_agent)
        except Exception as exc:
            _mark_failed(states.suggestion_agent, exc)

    return _finalize_analysis(db, analysis, states)


def prepare_retry(
    db: Session,
    analysis_id: str,
    targets: list[RetryTarget] | None = None,
) -> tuple[AnalysisRecord, list[RetryTarget]]:
    analysis = get_analysis(db, analysis_id)
    if analysis.status == AnalysisStatus.PROCESSING.value:
        raise AppError(
            ErrorCode.ANALYSIS_IN_PROGRESS,
            details={"analysisId": analysis_id},
        )

    states = ProviderStates.model_validate(analysis.provider_states)
    failed: list[RetryTarget] = [
        name
        for name in ("scoreAgent", "suggestionAgent")
        if _provider_state(states, name).status is ProviderStatus.FAILED
    ]
    selected = targets if targets is not None else failed
    if not selected or any(name not in failed for name in selected):
        raise AppError(
            ErrorCode.ANALYSIS_NOT_RETRYABLE,
            details={"analysisId": analysis_id, "failedProviders": failed},
        )

    original_status = analysis.status
    for name in selected:
        state = _provider_state(states, name)
        state.status = ProviderStatus.QUEUED
        state.error_code = None
        state.error_message = None
    result = db.execute(
        update(AnalysisRecord)
        .where(
            AnalysisRecord.id == analysis_id,
            AnalysisRecord.status == original_status,
        )
        .values(
            status=AnalysisStatus.PROCESSING.value,
            provider_states=states.model_dump(by_alias=True, mode="json"),
            completed_at=None,
            updated_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        current = get_analysis(db, analysis_id)
        code = (
            ErrorCode.ANALYSIS_IN_PROGRESS
            if current.status == AnalysisStatus.PROCESSING.value
            else ErrorCode.ANALYSIS_NOT_RETRYABLE
        )
        raise AppError(code, details={"analysisId": analysis_id})
    db.commit()
    db.refresh(analysis)
    return analysis, selected


def retry_payload(
    analysis: AnalysisRecord, retrying_providers: list[RetryTarget]
) -> dict[str, object]:
    payload = RetryAnalysisResult(
        id=analysis.id,
        status=AnalysisStatus(analysis.status),
        retrying_providers=retrying_providers,
        providers=ProviderStates.model_validate(analysis.provider_states),
        updated_at=analysis.updated_at,
    )
    return payload.model_dump(by_alias=True, mode="json")


def update_suggestion(
    db: Session,
    suggestion_id: str,
    *,
    status: UpdateSuggestionStatus,
    edited_text: str | None,
) -> SuggestionRecord:
    suggestion = db.get(SuggestionRecord, suggestion_id)
    if suggestion is None:
        raise AppError(
            ErrorCode.SUGGESTION_NOT_FOUND,
            details={"suggestionId": suggestion_id},
        )
    if suggestion.status != SuggestionStatus.PENDING.value:
        raise AppError(
            ErrorCode.SUGGESTION_STATE_CONFLICT,
            details={"suggestionId": suggestion_id, "status": suggestion.status},
        )

    analysis = get_analysis(db, suggestion.analysis_id)
    version = version_service.get_version(db, analysis.resume_version_id)
    draft = db.execute(
        select(Draft).where(Draft.resume_id == version.resume_id)
    ).scalar_one_or_none()
    if draft is not None and draft.base_version_id != version.id:
        raise AppError(
            ErrorCode.SUGGESTION_STATE_CONFLICT,
            "当前草稿已基于其他版本，不能应用旧分析建议。",
            details={"suggestionId": suggestion_id},
        )
    if draft is not None and draft.analysis_id not in (None, analysis.id):
        raise AppError(
            ErrorCode.SUGGESTION_STATE_CONFLICT,
            "当前优化草稿属于其他分析，不能混合应用建议。",
            details={"suggestionId": suggestion_id},
        )
    document = (
        ResumeDocument.model_validate(draft.document)
        if draft is not None
        else version_service.load_document(version)
    )
    found = document.find_item(suggestion.section_id, suggestion.item_id)
    if found is None:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "建议引用的原始条目不存在。",
            details={"suggestionId": suggestion_id},
        )
    _, item = found
    item.content = (
        suggestion.suggested
        if status == "accepted"
        else suggestion.original
        if status == "rejected"
        else edited_text or ""
    )

    changed_at = utcnow()
    result = db.execute(
        update(SuggestionRecord)
        .where(
            SuggestionRecord.id == suggestion_id,
            SuggestionRecord.status == SuggestionStatus.PENDING.value,
        )
        .values(status=status, edited_text=edited_text, updated_at=changed_at)
    )
    if result.rowcount != 1:
        db.rollback()
        raise AppError(
            ErrorCode.SUGGESTION_STATE_CONFLICT,
            details={"suggestionId": suggestion_id},
        )

    if draft is None:
        db.add(
            Draft(
                id=new_id("draft"),
                resume_id=version.resume_id,
                base_version_id=version.id,
                analysis_id=analysis.id,
                document=document.to_storage(),
                updated_at=changed_at,
            )
        )
    else:
        draft_result = db.execute(
            update(Draft)
            .where(
                Draft.id == draft.id,
                Draft.updated_at == draft.updated_at,
                or_(Draft.analysis_id.is_(None), Draft.analysis_id == analysis.id),
            )
            .values(
                base_version_id=version.id,
                analysis_id=analysis.id,
                document=document.to_storage(),
                updated_at=changed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if draft_result.rowcount != 1:
            db.rollback()
            raise AppError(
                ErrorCode.SUGGESTION_STATE_CONFLICT,
                "优化草稿已被其它请求更新，请重试。",
                details={"suggestionId": suggestion_id},
            )
    resume = db.get(Resume, version.resume_id)
    if resume is not None:
        resume.updated_at = changed_at
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            ErrorCode.SUGGESTION_STATE_CONFLICT,
            "优化草稿已被其它请求更新，请重试。",
            details={"suggestionId": suggestion_id},
        ) from exc
    db.refresh(suggestion)
    return suggestion


def suggestion_update_payload(suggestion: SuggestionRecord) -> dict[str, object]:
    payload = UpdateSuggestionResult(
        id=suggestion.id,
        analysis_id=suggestion.analysis_id,
        section_id=suggestion.section_id,
        item_id=suggestion.item_id,
        status=suggestion.status,
        edited_text=suggestion.edited_text,
        updated_at=suggestion.updated_at,
    )
    return payload.model_dump(by_alias=True, mode="json")


def rewrite_suggestion(
    db: Session, suggestion_id: str, current_content: str, document: ResumeDocument | None = None,
) -> dict[str, str]:
    from app.core.config import settings
    from app.services.analysis.deepseek import rewrite_content
    from app.services import resume_service

    if settings.analysis_provider.lower() != "deepseek":
        raise AppError(ErrorCode.ANALYSIS_PROVIDER_ERROR, "AI 改写需要启用 DeepSeek，演示数据不能用于真实改写。", status_code=503)
    suggestion = db.get(SuggestionRecord, suggestion_id)
    if suggestion is None:
        raise AppError(ErrorCode.SUGGESTION_NOT_FOUND)
    if suggestion.status != SuggestionStatus.PENDING.value:
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "该建议已处理，请重新分析。")
    analysis = get_analysis(db, suggestion.analysis_id)
    version = version_service.get_version(db, analysis.resume_version_id)
    current = document if document is not None else resume_service.get_draft_document(db, version.resume_id)
    found = current.find_item(suggestion.section_id, suggestion.item_id) if current else None
    if found is None or found[1].content != current_content:
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "当前内容已变化，请保存后重新生成改写。")
    result = rewrite_content(
        fields=found[1].fields,
        content=current_content,
        jd_text=analysis.jd_text,
        advice=f"{suggestion.reason}\n参考表达（并非新增事实依据）：{suggestion.suggested}",
    )
    return {"original": current_content, "rewritten": result.rewritten, "explanation": result.explanation}


def confirm_preview(
    db: Session, suggestion_id: str, *, original: str, replacement: str, document: ResumeDocument,
) -> ResumeDocument:
    suggestion = db.get(SuggestionRecord, suggestion_id)
    if suggestion is None:
        raise AppError(ErrorCode.SUGGESTION_NOT_FOUND)
    found = document.find_item(suggestion.section_id, suggestion.item_id)
    if found is None or found[1].content != original:
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "预览原文已修改，请重新生成改写。")
    result = db.execute(
        update(SuggestionRecord)
        .where(SuggestionRecord.id == suggestion_id, SuggestionRecord.status == SuggestionStatus.PENDING.value)
        .values(status=SuggestionStatus.EDITED.value, edited_text=replacement, updated_at=utcnow())
        .returning(SuggestionRecord.id)
    )
    if result.scalar_one_or_none() is None:
        db.rollback()
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "该建议已处理，请重新分析。")
    found[1].content = replacement
    db.commit()
    return document


def confirm_suggestion(
    db: Session, suggestion_id: str, *, original: str, replacement: str,
    document: ResumeDocument, expected_updated_at: datetime,
) -> Draft:
    suggestion = db.get(SuggestionRecord, suggestion_id)
    if suggestion is None:
        raise AppError(ErrorCode.SUGGESTION_NOT_FOUND)
    if suggestion.status != SuggestionStatus.PENDING.value:
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "建议已经处理，请重新分析。")
    analysis = get_analysis(db, suggestion.analysis_id)
    version = version_service.get_version(db, analysis.resume_version_id)
    draft = db.execute(select(Draft).where(Draft.resume_id == version.resume_id)).scalar_one_or_none()
    if draft is None:
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "当前简历内容已不存在，请刷新。")
    expected = expected_updated_at.astimezone(timezone.utc).replace(tzinfo=None)
    if draft.updated_at != expected:
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "简历已在其他页面更新，请重新打开后生成改写。")
    current = ResumeDocument.model_validate(draft.document).find_item(suggestion.section_id, suggestion.item_id)
    proposed = document.find_item(suggestion.section_id, suggestion.item_id)
    if current is None or proposed is None or current[1].content != original or proposed[1].content != original:
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "原文已修改或条目已删除，请重新生成 AI 改写。")
    proposed[1].content = replacement
    result = db.execute(
        update(SuggestionRecord)
        .where(SuggestionRecord.id == suggestion.id, SuggestionRecord.status == SuggestionStatus.PENDING.value)
        .values(status=SuggestionStatus.EDITED.value, edited_text=replacement, updated_at=utcnow())
        .returning(SuggestionRecord.id)
    )
    if result.scalar_one_or_none() is None:
        db.rollback()
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT)
    changed = db.execute(
        update(Draft)
        .where(Draft.id == draft.id, Draft.updated_at == expected)
        .values(document=document.to_storage(), analysis_id=analysis.id, updated_at=utcnow())
        .returning(Draft.id)
        .execution_options(synchronize_session=False)
    )
    if changed.scalar_one_or_none() is None:
        db.rollback()
        raise AppError(ErrorCode.SUGGESTION_STATE_CONFLICT, "简历已被其他请求修改，请刷新后重试。")
    resume = db.get(Resume, version.resume_id)
    if resume is not None:
        resume.updated_at = utcnow()
    db.commit()
    db.refresh(draft)
    return draft


def create_optimized_version(db: Session, analysis_id: str) -> ResumeVersion:
    analysis = get_analysis(db, analysis_id)
    if analysis.status == AnalysisStatus.PROCESSING.value:
        raise AppError(
            ErrorCode.ANALYSIS_IN_PROGRESS,
            details={"analysisId": analysis_id},
        )
    handled_statuses = {
        SuggestionStatus.ACCEPTED.value,
        SuggestionStatus.REJECTED.value,
        SuggestionStatus.EDITED.value,
    }
    if not any(item.status in handled_statuses for item in analysis.suggestions):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "当前分析尚未确认任何优化建议。",
            details={"analysisId": analysis_id},
        )

    base_version = version_service.get_version(db, analysis.resume_version_id)
    draft = db.execute(
        select(Draft).where(Draft.resume_id == base_version.resume_id)
    ).scalar_one_or_none()
    if (
        draft is None
        or draft.base_version_id != base_version.id
        or draft.analysis_id != analysis.id
    ):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "当前没有基于该分析版本的优化草稿。",
            details={
                "analysisId": analysis_id,
                "resumeVersionId": base_version.id,
            },
        )

    document = ResumeDocument.model_validate(draft.document)
    return version_service.create_version(
        db,
        resume_id=base_version.resume_id,
        source=VersionSource.OPTIMIZED,
        document=document,
        base_version_id=base_version.id,
    )


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


def _provider_state(states: ProviderStates, name: RetryTarget) -> ProviderState:
    return states.score_agent if name == "scoreAgent" else states.suggestion_agent


def _store_new_suggestions(
    db: Session,
    analysis_id: str,
    result: SuggestionProviderResult,
) -> None:
    existing = {
        (item.section_id, item.item_id, item.target_field)
        for item in db.execute(
            select(SuggestionRecord).where(SuggestionRecord.analysis_id == analysis_id)
        ).scalars()
    }
    for item in result.suggestions:
        target = (item.section_id, item.item_id, item.target_field)
        if target in existing:
            continue
        db.add(
            SuggestionRecord(
                id=new_id("suggestion"),
                analysis_id=analysis_id,
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


def _document_items(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (section.get("id", ""), item.get("id", "")): item
        for section in document.get("sections", [])
        for item in section.get("items", [])
    }


def _provider_document(document: dict[str, Any]) -> dict[str, Any]:
    basic_info = document.get("basicInfo", {})
    return {
        "basicInfo": {"jobTarget": basic_info.get("jobTarget", "")},
        "sections": deepcopy(document.get("sections", [])),
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
        else ErrorCode.ANALYSIS_PROVIDER_ERROR.value
        if isinstance(exc, AppError) and exc.code is ErrorCode.ANALYSIS_PROVIDER_ERROR
        else "INVALID_PROVIDER_RESPONSE"
    )
    state.error_message = (
        "分析服务调用超时。"
        if state.error_code == "PROVIDER_TIMEOUT"
        else exc.message
        if state.error_code == ErrorCode.ANALYSIS_PROVIDER_ERROR.value
        and isinstance(exc, AppError)
        else "分析服务返回了无效结果。"
    )


def _finalize_analysis(
    db: Session,
    analysis: AnalysisRecord,
    states: ProviderStates,
) -> AnalysisRecord:
    succeeded = sum(
        state.status is ProviderStatus.SUCCEEDED
        for state in (states.score_agent, states.suggestion_agent)
    )
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