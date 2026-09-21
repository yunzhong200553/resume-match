"""FastAPI 应用装配。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import api_router
from app.core.config import settings
from app.core.errors import AppError, ErrorCode, error_payload
from app.core.middleware import RequestIdMiddleware, current_request_id
from app.db.migrate import run_migrations

logger = logging.getLogger("resume_match")

DESCRIPTION = (
    "简历智造 ResumeMatch 后端。模块 A 负责简历构建、拆分、版本与共享导出；"
    "所有响应统一为 {data, requestId}，错误统一为 {error, requestId}。"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    if settings.auto_migrate:
        run_migrations()
        logger.info("数据库迁移已执行到 head")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ResumeMatch API",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        # 本机前端（Vite 默认端口）与 Playwright 调试使用
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(api_router, prefix="/api")
    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        logger.warning("业务异常 %s: %s", exc.code.value, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(current_request_id()),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details: dict[str, Any] = {
            "errors": [
                {
                    "loc": [str(part) for part in error.get("loc", [])],
                    "msg": str(error.get("msg", "")),
                    "type": str(error.get("type", "")),
                }
                for error in exc.errors()
            ]
        }
        return JSONResponse(
            status_code=422,
            content=error_payload(
                ErrorCode.VALIDATION_ERROR,
                "请求参数校验失败。",
                details,
                current_request_id(),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                "HTTP_ERROR",
                str(exc.detail),
                {"statusCode": exc.status_code},
                current_request_id(),
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                ErrorCode.INTERNAL_ERROR,
                details={},
                request_id=current_request_id(),
            ),
        )


app = create_app()
