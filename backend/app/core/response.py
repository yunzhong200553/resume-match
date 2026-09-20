"""统一成功响应包装：``{"data": ..., "requestId": ...}``。"""

from __future__ import annotations

from typing import Any

from app.core.middleware import current_request_id


def envelope(data: Any, request_id: str | None = None) -> dict[str, Any]:
    return {"data": data, "requestId": request_id or current_request_id()}
