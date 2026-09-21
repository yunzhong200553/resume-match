"""导出模板清单。

模板为人工提供的 Word 文件，渲染契约见 ``docs/template-contract.md``：
模板只需包含 ``{{basicInfo.name}}`` 这类占位符段落，以及 ``{{SECTIONS}}``
锚点段落（可选 ``{{SKILLS}}``），渲染器负责把模块与条目填进锚点位置。

当前只启用一份模板（格式取自参考简历）。第二份模板由人工提供后，
在 ``TEMPLATES`` 中追加一项即可，接口按 id 暴露，调用方无需改动。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError, ErrorCode


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    id: str
    name: str
    description: str
    filename: str
    name_style: str = "ResumeName"
    contact_style: str = "ResumeContact"
    heading_style: str = "ResumeSectionHeading"
    item_style: str = "ResumeItem"
    content_style: str = "ResumeItemContent"


TEMPLATES: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        id="classic_single_column",
        name="经典单栏",
        description="按参考简历格式提取：微软雅黑标题、名称/角色/日期三列对齐、单栏排版。",
        filename="classic_single_column.docx",
    ),
)

TEMPLATE_FORMATS = ("docx", "pdf")


def list_templates() -> list[TemplateSpec]:
    return list(TEMPLATES)


def get_template(template_id: str) -> TemplateSpec:
    for spec in TEMPLATES:
        if spec.id == template_id:
            return spec
    raise AppError(
        ErrorCode.TEMPLATE_NOT_FOUND,
        details={"templateId": template_id, "available": [spec.id for spec in TEMPLATES]},
    )


def template_path(spec: TemplateSpec) -> Path:
    path = settings.template_dir / spec.filename
    if not path.exists():
        raise AppError(
            ErrorCode.TEMPLATE_NOT_FOUND,
            f"模板文件 {spec.filename} 不存在，请执行 scripts/build_template_from_resume.py 生成。",
            details={"templateId": spec.id, "path": str(path)},
        )
    return path
