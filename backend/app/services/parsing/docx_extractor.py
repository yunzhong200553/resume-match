"""DOCX 内容提取（python-docx）。

按文档顺序输出「行」：

* 普通段落 -> 一行；
* 表格行 -> ``单元格1 | 单元格2 | 单元格3``，与参考简历的
  ``名称 | 角色 | 日期`` 三列布局一致；
* 合并单元格产生的重复文本会被去重，避免同一段描述出现三次。
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.core.errors import AppError, ErrorCode
from app.services.parsing.docx_blocks import iter_block_items


def extract_text(path: Path) -> str:
    try:
        document = Document(str(path))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise AppError(
            ErrorCode.FILE_TYPE_NOT_SUPPORTED,
            "DOCX 文件无法解析，请确认文件未损坏。",
            details={"reason": str(exc)},
        ) from exc

    lines: list[str] = []
    for block in iter_block_items(document):
        if isinstance(block, Paragraph):
            lines.extend(_paragraph_lines(block.text))
        elif isinstance(block, Table):
            for row in block.rows:
                lines.extend(_row_lines(row))
    return "\n".join(line for line in lines if line.strip())


def _paragraph_lines(text: str) -> list[str]:
    return [segment.strip() for segment in text.splitlines()]


def _row_lines(row) -> list[str]:
    unique: list[str] = []
    for cell in row.cells:
        text = cell.text
        # 横向合并单元格会在 row.cells 中重复出现，去重后只保留一份
        if text.strip() and (not unique or unique[-1] != text):
            unique.append(text)
    if not unique:
        return []
    if len(unique) == 1:
        # 描述的合并行：保留原换行，让拆分器能看到「项目背景 / 项目内容 / 成果」结构
        return [line.strip() for line in unique[0].splitlines() if line.strip()]
    return [
        " | ".join(" ".join(line.split()) for line in cell.splitlines() if line.strip())
        for cell in unique
    ]
