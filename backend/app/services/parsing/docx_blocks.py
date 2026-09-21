"""按文档顺序遍历 DOCX 段落与表格。

``document.paragraphs`` 会丢掉表格位置信息，而参考简历格式（``名称 | 角色 | 日期``
三列表格 + 合并的描述行）正是靠表格排版的，因此这里按 body 顺序取块。
"""

from __future__ import annotations

from collections.abc import Iterator

from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


def iter_block_items(parent) -> Iterator[Paragraph | Table]:
    if isinstance(parent, DocxDocument):
        parent_element = parent.element.body
    else:  # 表格单元格
        parent_element = parent._tc

    for child in parent_element.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def iter_paragraphs(parent, *, include_tables: bool = True) -> Iterator[Paragraph]:
    """遍历段落；``include_tables=True`` 时同时展开表格单元格内的段落。"""

    for block in iter_block_items(parent):
        if isinstance(block, Paragraph):
            yield block
        elif include_tables:
            for row in block.rows:
                for cell in row.cells:
                    yield from iter_paragraphs(cell)
