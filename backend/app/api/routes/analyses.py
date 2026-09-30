"""JD 分析任务接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks

from app.api.deps import DbSession
from app.core.response import envelope
from app.schemas.analysis import CreateAnalysisRequest, RetryAnalysisRequest
from app.services.analysis import service

router = APIRouter(prefix="/analyses", tags=["JD 分析"])


@router.post("", status_code=202, summary="创建 JD 分析")
def create_analysis(
    payload: CreateAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> dict[str, Any]:
    analysis = service.create_analysis(
        db,
        resume_version_id=payload.resume_version_id,
        jd_text=payload.jd_text,
    )
    response = envelope(service.create_payload(analysis))
    background_tasks.add_task(service.run_analysis, db, analysis.id)
    return response


@router.get("/{analysis_id}", summary="获取 JD 分析")
def get_analysis(analysis_id: str, db: DbSession) -> dict[str, Any]:
    return envelope(service.analysis_payload(service.get_analysis(db, analysis_id)))


@router.post("/{analysis_id}/retry", status_code=202, summary="重试 JD 分析")
def retry_analysis(
    analysis_id: str,
    payload: RetryAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> dict[str, Any]:
    analysis, targets = service.prepare_retry(db, analysis_id, payload.targets)
    response = envelope(service.retry_payload(analysis, targets))
    background_tasks.add_task(service.run_analysis, db, analysis.id, None, targets)
    return response


@router.post(
    "/{analysis_id}/versions",
    status_code=201,
    summary="保存 optimized 简历版本",
)
def create_optimized_version(analysis_id: str, db: DbSession) -> dict[str, Any]:
    version = service.create_optimized_version(db, analysis_id)
    return envelope(version.to_payload())