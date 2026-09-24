"""统一错误契约。

错误码与 HTTP 状态的映射以 README 第 7.1 节为准；``EXPORT_NOT_FOUND``、
``TEMPLATE_NOT_FOUND``、``INTERNAL_ERROR`` 为本模块补充的扩展码，
用于覆盖 README 未列举但实现必需的场景，详见 ``docs/api-extensions.md``。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class ErrorCode(str, Enum):
    # ---- README 7.1 已定义 ----
    VALIDATION_ERROR = "VALIDATION_ERROR"
    FILE_TYPE_NOT_SUPPORTED = "FILE_TYPE_NOT_SUPPORTED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_SCANNED_PDF = "UNSUPPORTED_SCANNED_PDF"
    RESUME_NOT_FOUND = "RESUME_NOT_FOUND"
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    JD_TEXT_TOO_SHORT = "JD_TEXT_TOO_SHORT"
    JD_TEXT_TOO_LONG = "JD_TEXT_TOO_LONG"
    ANALYSIS_NOT_FOUND = "ANALYSIS_NOT_FOUND"
    SUGGESTION_NOT_FOUND = "SUGGESTION_NOT_FOUND"
    ANALYSIS_IN_PROGRESS = "ANALYSIS_IN_PROGRESS"
    ANALYSIS_NOT_RETRYABLE = "ANALYSIS_NOT_RETRYABLE"
    SUGGESTION_STATE_CONFLICT = "SUGGESTION_STATE_CONFLICT"
    ANALYSIS_PROVIDER_ERROR = "ANALYSIS_PROVIDER_ERROR"
    ANALYSIS_TIMEOUT = "ANALYSIS_TIMEOUT"
    EXPORT_DEPENDENCY_MISSING = "EXPORT_DEPENDENCY_MISSING"
    EXPORT_FAILED = "EXPORT_FAILED"

    # ---- 本模块扩展 ----
    EXPORT_NOT_FOUND = "EXPORT_NOT_FOUND"
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


STATUS_BY_CODE: Mapping[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.FILE_TYPE_NOT_SUPPORTED: 415,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_SCANNED_PDF: 422,
    ErrorCode.RESUME_NOT_FOUND: 404,
    ErrorCode.VERSION_NOT_FOUND: 404,
    ErrorCode.JD_TEXT_TOO_SHORT: 422,
    ErrorCode.JD_TEXT_TOO_LONG: 413,
    ErrorCode.ANALYSIS_NOT_FOUND: 404,
    ErrorCode.SUGGESTION_NOT_FOUND: 404,
    ErrorCode.ANALYSIS_IN_PROGRESS: 409,
    ErrorCode.ANALYSIS_NOT_RETRYABLE: 409,
    ErrorCode.SUGGESTION_STATE_CONFLICT: 409,
    ErrorCode.ANALYSIS_PROVIDER_ERROR: 502,
    ErrorCode.ANALYSIS_TIMEOUT: 504,
    ErrorCode.EXPORT_DEPENDENCY_MISSING: 503,
    ErrorCode.EXPORT_FAILED: 500,
    ErrorCode.EXPORT_NOT_FOUND: 404,
    ErrorCode.TEMPLATE_NOT_FOUND: 404,
    ErrorCode.INTERNAL_ERROR: 500,
}

DEFAULT_MESSAGE_BY_CODE: Mapping[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "请求字段或模型输出不符合契约。",
    ErrorCode.FILE_TYPE_NOT_SUPPORTED: "仅支持 PDF 或 DOCX 文件。",
    ErrorCode.FILE_TOO_LARGE: "文件超过大小限制。",
    ErrorCode.UNSUPPORTED_SCANNED_PDF: "未检测到可提取文本，请改用手动录入。",
    ErrorCode.RESUME_NOT_FOUND: "简历不存在。",
    ErrorCode.VERSION_NOT_FOUND: "简历版本不存在。",
    ErrorCode.JD_TEXT_TOO_SHORT: "JD 文本不能少于 50 个字符。",
    ErrorCode.JD_TEXT_TOO_LONG: "JD 文本不能超过 20,000 个字符。",
    ErrorCode.ANALYSIS_NOT_FOUND: "分析记录不存在。",
    ErrorCode.SUGGESTION_NOT_FOUND: "建议不存在。",
    ErrorCode.ANALYSIS_IN_PROGRESS: "分析正在执行，暂时不能重试。",
    ErrorCode.ANALYSIS_NOT_RETRYABLE: "当前没有可重试的分析任务。",
    ErrorCode.SUGGESTION_STATE_CONFLICT: "建议状态已发生变化。",
    ErrorCode.ANALYSIS_PROVIDER_ERROR: "分析服务调用或响应校验失败。",
    ErrorCode.ANALYSIS_TIMEOUT: "分析服务调用超时。",
    ErrorCode.EXPORT_DEPENDENCY_MISSING: "未找到 LibreOffice，无法生成 PDF。",
    ErrorCode.EXPORT_FAILED: "模板渲染或格式转换失败。",
    ErrorCode.EXPORT_NOT_FOUND: "导出记录不存在。",
    ErrorCode.TEMPLATE_NOT_FOUND: "导出模板不存在。",
    ErrorCode.INTERNAL_ERROR: "服务内部错误。",
}


class AppError(Exception):
    """业务异常，统一由异常处理器转换为错误响应体。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGE_BY_CODE.get(code, "请求处理失败。")
        self.details = details or {}
        self.status_code = status_code or STATUS_BY_CODE.get(code, 500)
        super().__init__(f"{code.value}: {self.message}")

    def to_payload(self, request_id: str = "") -> dict[str, Any]:
        return error_payload(self.code, self.message, self.details, request_id)


def error_payload(
    code: ErrorCode | str,
    message: str | None = None,
    details: Mapping[str, Any] | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    code_value = code.value if isinstance(code, ErrorCode) else str(code)
    if message is None:
        resolved = code_of(code_value)
        message = DEFAULT_MESSAGE_BY_CODE.get(resolved, "请求处理失败。") if resolved else "请求处理失败。"
    return {
        "error": {
            "code": code_value,
            "message": message,
            "details": dict(details or {}),
        },
        "requestId": request_id,
    }


def code_of(code_value: str) -> ErrorCode | None:
    try:
        return ErrorCode(code_value)
    except ValueError:
        return None
