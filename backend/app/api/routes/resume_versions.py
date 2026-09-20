"""版本快照查询接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.response import envelope
from app.services import version_service

router = APIRouter()


@router.get("/resume-versions/{version_id}", summary="获取指定版本快照")
def get_version(version_id: str, db: DbSession) -> dict[str, Any]:
    version = version_service.get_version(db, version_id)
    return envelope(version.to_payload())
