"""文件导入：校验、落盘与文本拆分。

校验顺序：扩展名 -> MIME -> 大小（README 10）。落盘使用随机文件名，
响应只回传展示用文件名与大小，不回传服务器路径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.schemas.resume_document import ResumeDocument
from app.services.parsing import docx_extractor, pdf_extractor
from app.services.parsing.text_parser import parse_resume_text

ALLOWED_EXTENSIONS: dict[str, str] = {".pdf": "pdf", ".docx": "docx"}

#: 允许的 MIME 白名单。部分 Windows 客户端发送通用类型，因此保留 octet-stream/zip，
#: 但仍然要求扩展名可解析（解析环节会再次校验文件是否可读）。
ALLOWED_MIME: dict[str, set[str]] = {
    ".pdf": {"application/pdf", "application/octet-stream", "application/x-pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    },
}

GENERIC_MIME = {"", "application/octet-stream"}


@dataclass(slots=True)
class ImportOutcome:
    document: ResumeDocument
    warnings: list[str] = field(default_factory=list)
    filename: str = ""
    file_format: str = ""
    size_bytes: int = 0
    stored_path: Path | None = None


def import_resume_bytes(*, filename: str, content_type: str | None, data: bytes) -> ImportOutcome:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise AppError(
            ErrorCode.FILE_TYPE_NOT_SUPPORTED,
            details={"filename": filename, "allowed": sorted(ALLOWED_EXTENSIONS)},
        )

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in GENERIC_MIME and mime not in ALLOWED_MIME[suffix]:
        raise AppError(
            ErrorCode.FILE_TYPE_NOT_SUPPORTED,
            "文件类型与扩展名不匹配。",
            details={"filename": filename, "contentType": mime},
        )

    size = len(data)
    if size > settings.max_upload_bytes:
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            f"文件超过 {settings.max_upload_mb} MB 限制。",
            details={"sizeBytes": size, "maxBytes": settings.max_upload_bytes},
        )
    if size == 0:
        raise AppError(ErrorCode.FILE_TYPE_NOT_SUPPORTED, "文件内容为空。")

    stored_path = _store_upload(suffix, data)
    try:
        text = _extract_text(suffix, stored_path)
    except Exception:
        # 解析失败不保留无用的原件
        stored_path.unlink(missing_ok=True)
        raise

    outcome = parse_resume_text(text)
    return ImportOutcome(
        document=outcome.document,
        warnings=outcome.warnings,
        filename=Path(filename).name,
        file_format=ALLOWED_EXTENSIONS[suffix],
        size_bytes=size,
        stored_path=stored_path,
    )


def _store_upload(suffix: str, data: bytes) -> Path:
    settings.ensure_dirs()
    path = settings.upload_dir / f"{new_id('upload')}{suffix}"
    path.write_bytes(data)
    return path


def _extract_text(suffix: str, path: Path) -> str:
    if suffix == ".pdf":
        return pdf_extractor.extract_text(path)
    return docx_extractor.extract_text(path)
