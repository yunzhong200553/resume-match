"""请求上下文：为每个请求生成 requestId 并透出响应头。"""

from __future__ import annotations

from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.ids import new_request_id

_REQUEST_ID: ContextVar[str] = ContextVar("resume_match_request_id", default="")
REQUEST_ID_HEADER = "X-Request-Id"


def current_request_id() -> str:
    return _REQUEST_ID.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """生成或沿用客户端传入的请求 ID，写入 state、上下文变量与响应头。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        request.state.request_id = request_id
        token = _REQUEST_ID.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _REQUEST_ID.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
