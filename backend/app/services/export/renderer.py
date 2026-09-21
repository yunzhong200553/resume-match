"""DOCX 模板渲染。

渲染规则：

1. ``{{basicInfo.name}}``、``{{resumeTitle}}``、``{{exportDate}}`` 等占位符就地替换；
2. ``{{SECTIONS}}`` 锚点段落被替换为该版本的模块与条目；
   若模板里同时存在 ``{{SKILLS}}``，``{{SECTIONS}}`` 会跳过技能模块，避免重复；
3. 条目标题行按模板样式输出 ``名称 <Tab> 角色 <Tab> 起止时间``，
   由样式里的制表位对齐成三列（与参考简历的表格版面一致，但不依赖表格）；
4. 未识别的字段与描述文本一律保留，不丢内容。
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from app.schemas.resume_document import ResumeDocument, SectionItem, SectionType
from app.services.export.templates import TemplateSpec
from app.services.parsing.docx_blocks import iter_paragraphs

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
MARKER_SECTIONS = "{{SECTIONS}}"
MARKER_SKILLS = "{{SKILLS}}"

PERIOD_KEYS = {"startDate", "endDate"}

#: 每个模块的「标题行」列定义：每一列由若干字段拼成，最后拼接顺序即显示顺序
FIELD_COLUMNS: dict[SectionType, tuple[tuple[str, ...], ...]] = {
    SectionType.education: (("school",), ("major", "degree"), ("startDate", "endDate")),
    SectionType.experience: (("company",), ("role",), ("startDate", "endDate")),
    SectionType.project: (("name",), ("role",), ("startDate", "endDate")),
    SectionType.award: (("name",), ("date", "startDate", "endDate")),
    SectionType.skill: (("name",),),
    SectionType.custom: (),
}

KNOWN_KEYS = frozenset(
    key for columns in FIELD_COLUMNS.values() for column in columns for key in column
) | {"category"}


@dataclass(slots=True)
class _Marker:
    paragraph: Paragraph
    kind: str  # sections | skills


def render_resume(
    document: ResumeDocument,
    *,
    template_path: Path,
    output_path: Path,
    template: TemplateSpec,
    resume_title: str = "",
    export_date: str | None = None,
) -> Path:
    docx = DocxDocument(str(template_path))
    markers = _collect_markers(docx)
    has_skill_marker = any(marker.kind == "skills" for marker in markers)

    for marker in markers:
        if marker.kind == "skills":
            _render_sections(marker.paragraph, document, template, only=SectionType.skill)
        else:
            skip = {SectionType.skill} if has_skill_marker else set()
            _render_sections(marker.paragraph, document, template, skip=skip)
        _remove_paragraph(marker.paragraph)

    values = {
        "basicInfo.name": document.basic_info.name,
        "basicInfo.phone": document.basic_info.phone,
        "basicInfo.email": document.basic_info.email,
        "basicInfo.location": document.basic_info.location,
        "basicInfo.jobTarget": document.basic_info.job_target,
        "resumeTitle": resume_title,
        "exportDate": export_date or date.today().isoformat(),
    }
    for paragraph in iter_paragraphs(docx):
        _replace_placeholders(paragraph, values)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    docx.save(str(output_path))
    return output_path


# --------------------------------------------------------------------------
# 锚点与段落操作
# --------------------------------------------------------------------------


def _collect_markers(docx: DocxDocument) -> list[_Marker]:
    markers: list[_Marker] = []
    for paragraph in iter_paragraphs(docx):
        text = paragraph.text
        if MARKER_SECTIONS in text:
            markers.append(_Marker(paragraph, "sections"))
        elif MARKER_SKILLS in text:
            markers.append(_Marker(paragraph, "skills"))
    return markers


def _render_sections(
    marker: Paragraph,
    document: ResumeDocument,
    template: TemplateSpec,
    *,
    skip: set[SectionType] | None = None,
    only: SectionType | None = None,
) -> None:
    skip = skip or set()
    for section in document.ordered_sections():
        if only is not None and section.type != only:
            continue
        if section.type in skip:
            continue
        if not section.items:
            continue

        _insert_before(marker, section.title, template.heading_style)
        for item in document.ordered_items(section):
            title, content = format_item(item, section.type)
            if title:
                _insert_before(marker, title, template.item_style)
            for line in content.split("\n"):
                if line.strip():
                    _insert_before(marker, line.strip(), template.content_style)


def _insert_before(marker: Paragraph, text: str, style_name: str) -> Paragraph:
    """在锚点前插入段落，继承锚点段落的段落属性（缩进、间距、对齐）。"""

    new_element = copy.deepcopy(marker._p)
    for child in list(new_element):
        if child.tag != qn("w:pPr"):
            new_element.remove(child)

    marker._p.addprevious(new_element)
    paragraph = Paragraph(new_element, marker._parent)
    paragraph.text = text
    _apply_style(paragraph, style_name)
    return paragraph


def _apply_style(paragraph: Paragraph, style_name: str) -> None:
    try:
        paragraph.style = style_name
    except KeyError:
        # 模板没有定义该样式时退回默认样式，不影响内容完整性
        pass


def _remove_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._p
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _replace_placeholders(paragraph: Paragraph, values: dict[str, str]) -> None:
    if "{{" not in paragraph.text:
        return

    def substitute(match: re.Match[str]) -> str:
        return values.get(match.group(1), "")

    for run in paragraph.runs:
        if "{{" in run.text:
            run.text = PLACEHOLDER_RE.sub(substitute, run.text)

    # 占位符被 Word 拆到多个 run 时，退化为整段重写
    if PLACEHOLDER_RE.search(paragraph.text):
        text = PLACEHOLDER_RE.sub(substitute, paragraph.text)
        if paragraph.runs:
            paragraph.runs[0].text = text
            for run in paragraph.runs[1:]:
                run.text = ""


# --------------------------------------------------------------------------
# 条目格式化
# --------------------------------------------------------------------------


def format_item(item: SectionItem, section_type: SectionType) -> tuple[str, str]:
    """返回 ``(标题行, 描述正文)``；标题行内的 ``\\t`` 由模板制表位对齐成列。"""

    if section_type is SectionType.skill:
        category = item.field_or_empty("category")
        if category:
            body = (item.content or item.field_or_empty("name")).strip().strip("。")
            return f"{category}：{body}".strip("："), ""
        return item.content.strip() or item.field_or_empty("name"), ""

    columns = FIELD_COLUMNS.get(section_type, ())
    if not columns:
        # 自定义模块没有固定字段，正文即标题
        return item.content.strip(), ""

    extras = [
        value.strip()
        for key, value in item.fields.items()
        if key not in KNOWN_KEYS and (value or "").strip()
    ]

    segments: list[str] = []
    for index, column in enumerate(columns):
        if any(key in PERIOD_KEYS for key in column):
            text = format_period(item.fields.get("startDate"), item.fields.get("endDate"))
        else:
            text = " ".join(
                item.field_or_empty(key) for key in column if item.field_or_empty(key)
            )
        if index == 1 and extras:
            text = " ".join([text, *extras]).strip()
        segments.append(text)
    if extras and len(segments) < 2:
        segments.append("、".join(extras))

    title = "\t".join(segments).strip()
    content = item.content.strip()
    if not title:
        return content, ""
    if content == title:
        content = ""
    return title, content


def format_period(start: str | None, end: str | None) -> str:
    start_text = (start or "").replace("-", ".").strip()
    end_text = (end or "").replace("-", ".").strip()
    if start_text and end_text:
        return f"{start_text} - {end_text}"
    return start_text or end_text
