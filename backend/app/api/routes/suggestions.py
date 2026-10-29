"""JD 分析建议处理接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.response import envelope
from app.schemas.analysis import ConfirmPreviewRequest, ConfirmSuggestionRequest, RewriteSuggestionRequest, UpdateSuggestionRequest
from app.services.analysis import service

router = APIRouter(prefix="/suggestions", tags=["JD 分析"])


@router.post("/{suggestion_id}/rewrite", summary="生成 AI 改写预览，不修改简历")
def rewrite_suggestion(suggestion_id: str, payload: RewriteSuggestionRequest, db: DbSession) -> dict[str, Any]:
    return envelope(service.rewrite_suggestion(db, suggestion_id, payload.current_content, payload.document))


@router.post("/{suggestion_id}/preview-confirm", summary="确认应用到独立 JD 排版，不覆盖基础简历")
def confirm_preview(suggestion_id: str, payload: ConfirmPreviewRequest, db: DbSession) -> dict[str, Any]:
    document = service.confirm_preview(
        db, suggestion_id, original=payload.original, replacement=payload.replacement, document=payload.document,
    )
    return envelope({"document": document.to_storage()})


@router.post("/{suggestion_id}/confirm", summary="用户确认后替换当前内容")
def confirm_suggestion(suggestion_id: str, payload: ConfirmSuggestionRequest, db: DbSession) -> dict[str, Any]:
    draft = service.confirm_suggestion(
        db, suggestion_id, original=payload.original, replacement=payload.replacement, document=payload.document,
        expected_updated_at=payload.expected_updated_at,
    )
    return envelope({"draft": draft.to_payload()})


@router.patch("/{suggestion_id}", summary="接受、拒绝或编辑建议")
def update_suggestion(
    suggestion_id: str,
    payload: UpdateSuggestionRequest,
    db: DbSession,
) -> dict[str, Any]:
    suggestion = service.update_suggestion(
        db,
        suggestion_id,
        status=payload.status,
        edited_text=payload.edited_text,
    )
    return envelope(service.suggestion_update_payload(suggestion))