"""文本型 PDF 内容提取（PyMuPDF）。

无可提取文本时抛出 ``UNSUPPORTED_SCANNED_PDF``，由接口层提示用户改用手动录入，
此时不产生任何结构化数据，用户已填写的内容不受影响。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf

from app.core.errors import AppError, ErrorCode

#: 少于该字符数视为「未检测到可提取文本」
MIN_EXTRACTED_CHARS = 20
LINE_CLUSTER_TOLERANCE = 3.0


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
        pages = [_page_text(page) for page in document]
    finally:
        document.close()

    text = "\n".join(pages).strip()
    if len("".join(text.split())) < MIN_EXTRACTED_CHARS:
        raise AppError(
            ErrorCode.UNSUPPORTED_SCANNED_PDF,
            details={"extractedLength": len(text)},
        )
    return text


def _page_text(page: Any) -> str:
    """按视觉行重建 PDF 文本。

    PDF 的内部内容流不一定等于阅读顺序。特别是由 WPS 等工具导出的简历，同行的
    公司、岗位和日期会被分成三个独立文本块；直接使用 ``get_text("text")`` 会令
    后续块先于同一行的其它字段出现，进而破坏模块和条目的识别。
    """

    blocks = page.get_text("blocks", sort=True)
    lines: list[list[tuple[float, str]]] = []
    current_y: float | None = None

    for block in blocks:
        x0, y0, _x1, _y1, text, *_rest = block
        clean_text = " ".join(str(text).split())
        if not clean_text:
            continue
        if current_y is None or abs(float(y0) - current_y) > LINE_CLUSTER_TOLERANCE:
            lines.append([])
            current_y = float(y0)
        lines[-1].append((float(x0), clean_text))

    return "\n".join(
        " ".join(text for _x0, text in sorted(line, key=lambda value: value[0]))
        for line in lines
    )
