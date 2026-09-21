"""文本型 PDF 内容提取（PyMuPDF）。

无可提取文本时抛出 ``UNSUPPORTED_SCANNED_PDF``，由接口层提示用户改用手动录入，
此时不产生任何结构化数据，用户已填写的内容不受影响。
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.core.errors import AppError, ErrorCode

#: 少于该字符数视为「未检测到可提取文本」
MIN_EXTRACTED_CHARS = 20


def extract_text(path: Path) -> str:
    try:
        document = pymupdf.open(str(path))
    except Exception as exc:  # pragma: no cover - 损坏文件属于异常路径
        raise AppError(
            ErrorCode.FILE_TYPE_NOT_SUPPORTED,
            "PDF 文件无法解析，请确认文件未损坏。",
            details={"reason": str(exc)},
        ) from exc

    try:
        if document.page_count == 0:
            raise AppError(ErrorCode.UNSUPPORTED_SCANNED_PDF)
        pages = [page.get_text("text") for page in document]
    finally:
        document.close()

    text = "\n".join(pages).strip()
    if len("".join(text.split())) < MIN_EXTRACTED_CHARS:
        raise AppError(
            ErrorCode.UNSUPPORTED_SCANNED_PDF,
            details={"extractedLength": len(text)},
        )
    return text
