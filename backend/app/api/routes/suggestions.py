"""JD 分析建议处理接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.response import envelope
from app.schemas.analysis import UpdateSuggestionRequest
from app.services.analysis import service

router = APIRouter(prefix="/suggestions", tags=["JD 分析"])


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