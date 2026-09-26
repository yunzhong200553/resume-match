"""按参考简历生成导出模板（脱敏占位版）。

思路：从参考简历里**只取格式**（页面设置、字体、字号、颜色），
把内容全部替换成占位符后写出模板文件。生成的模板不含任何个人信息，可以入库；
参考简历原件本身必须留在 .gitignore 覆盖的目录里。

用法::

    python scripts/build_template_from_resume.py
    python scripts/build_template_from_resume.py --source "路径/参考简历.docx"
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.shared import Cm, Pt, RGBColor

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import REPO_ROOT, settings  # noqa: E402

#: 参考简历缺失时使用的兜底格式（与参考简历实测值一致）
FALLBACK_FONT = "微软雅黑"
FALLBACK_HEADING_SIZE = 16.0
FALLBACK_BODY_SIZE = 10.5
FALLBACK_TEXT_COLOR = "0F1115"

SECTION_TITLE_HINTS = ("教育背景", "教育经历", "实习经历", "项目经历", "技能与工具", "技能")


@dataclass(slots=True)
class FormatProfile:
    """从参考简历提取出的格式参数。"""

    font: str = FALLBACK_FONT
    heading_size: float = FALLBACK_HEADING_SIZE
    body_size: float = FALLBACK_BODY_SIZE
    text_color: str = FALLBACK_TEXT_COLOR
    source: str = "内置默认值"

    def describe(self) -> str:
        return (
            f"字体={self.font} 标题={self.heading_size}pt 正文={self.body_size}pt "
            f"颜色=#{self.text_color}（来源：{self.source}）"
        )


def detect_reference_path(explicit: str | None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if settings.reference_resume_path:
        candidates.append(Path(settings.reference_resume_path))
    # 推荐把参考简历原件放在 private/（已被 .gitignore 覆盖），根目录作为兼容位置
    private_dir = REPO_ROOT / "private"
    if private_dir.is_dir():
        candidates.extend(sorted(private_dir.glob("*.docx")))
    candidates.extend(sorted(REPO_ROOT.glob("*.docx")))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def read_profile(source: Path | None) -> FormatProfile:
    """读取参考简历的字体与字号；读不到就退回内置默认值。"""

    if source is None:
        return FormatProfile()

    try:
        document = Document(str(source))
    except Exception as exc:  # pragma: no cover - 文件损坏属于异常路径
        print(f"[warn] 无法读取参考简历（{exc}），改用内置默认格式")
        return FormatProfile()

    heading_run = None
    body_run = None
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text or not paragraph.runs:
            continue
        run = paragraph.runs[0]
        if any(hint in text for hint in SECTION_TITLE_HINTS) and len(text) <= 12:
            heading_run = heading_run or run
        elif heading_run is not None and body_run is None:
            body_run = run

    if heading_run is None:
        # 表格排版的简历：模块标题也可能是表格文字，退化为扫描所有 run
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        text = paragraph.text.strip()
                        if not text or not paragraph.runs:
                            continue
                        if any(hint in text for hint in SECTION_TITLE_HINTS) and len(text) <= 12:
                            heading_run = paragraph.runs[0]
                            break
                    if heading_run is not None:
                        break
                if heading_run is not None:
                    break
            if heading_run is not None:
                break

    def pick(run, fallback_font: str, fallback_size: float) -> tuple[str, float]:
        if run is None:
            return fallback_font, fallback_size
        font_name = run.font.name or fallback_font
        if run._element.rPr is not None and run._element.rPr.rFonts is not None:
            east_asia = run._element.rPr.rFonts.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia"
            )
            font_name = east_asia or font_name
        size = run.font.size.pt if run.font.size else fallback_size
        return font_name, size

    font, heading_size = pick(heading_run, FALLBACK_FONT, FALLBACK_HEADING_SIZE)
    _, body_size = pick(body_run, font, FALLBACK_BODY_SIZE)
    color = FALLBACK_TEXT_COLOR
    if heading_run is not None and heading_run.font.color is not None and heading_run.font.color.rgb:
        color = str(heading_run.font.color.rgb)

    return FormatProfile(
        font=font,
        heading_size=heading_size,
        body_size=body_size,
        text_color=color,
        source=str(source),
    )


def copy_page_setup(source: Path | None, target: Document) -> None:
    if source is None:
        return
    try:
        source_document = Document(str(source))
    except Exception:  # pragma: no cover
        return
    source_section = source_document.sections[0]
    target_section = target.sections[0]
    for attribute in (
        "page_width",
        "page_height",
        "left_margin",
        "right_margin",
        "top_margin",
        "bottom_margin",
    ):
        value = getattr(source_section, attribute)
        if value is not None:
            setattr(target_section, attribute, value)


def build_styles(document: Document, profile: FormatProfile) -> None:
    styles = document.styles
    color = RGBColor.from_string(profile.text_color)

    normal = styles["Normal"]
    normal.font.name = profile.font
    normal.font.size = Pt(profile.body_size)
    normal.font.color.rgb = color
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.0

    def add_style(name: str, size: float, *, bold: bool = False, space_before: float = 0.0):
        if name in [style.name for style in styles]:
            return styles[name]
        style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = styles["Normal"]
        style.font.name = profile.font
        style.font.size = Pt(size)
        style.font.bold = bold
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(space_before)
        style.paragraph_format.space_after = Pt(2)
        style.paragraph_format.line_spacing = 1.0
        return style

    add_style("ResumeName", profile.heading_size + 2, bold=True)
    add_style("ResumeContact", profile.body_size)
    add_style("ResumeSectionHeading", profile.heading_size, bold=True, space_before=8)

    item_style = add_style("ResumeItem", profile.body_size, bold=True, space_before=4)
    # 「名称 <Tab> 角色 <Tab> 起止时间」三列对齐：中间左对齐，末尾右对齐
    tab_stops = item_style.paragraph_format.tab_stops
    tab_stops.add_tab_stop(Cm(6.8), WD_TAB_ALIGNMENT.LEFT)
    tab_stops.add_tab_stop(Cm(16.0), WD_TAB_ALIGNMENT.RIGHT)

    add_style("ResumeItemContent", profile.body_size)


def build_basic_info_table(document: Document, profile: FormatProfile) -> None:
    table = document.add_table(rows=2, cols=3)
    table.autofit = True

    cells = (
        ("姓名：{{basicInfo.name}}", "手机：{{basicInfo.phone}}", "邮箱：{{basicInfo.email}}"),
        ("所在地：{{basicInfo.location}}", "求职意向：{{basicInfo.jobTarget}}", ""),
    )
    for row_index, row_values in enumerate(cells):
        for column_index, text in enumerate(row_values):
            cell = table.cell(row_index, column_index)
            paragraph = cell.paragraphs[0]
            paragraph.text = text
            paragraph.style = document.styles["ResumeContact"]
            paragraph.paragraph_format.space_after = Pt(0)


def build_template(profile: FormatProfile, source: Path | None, output: Path) -> Path:
    document = Document()
    build_styles(document, profile)
    copy_page_setup(source, document)

    name_paragraph = document.add_paragraph("{{basicInfo.name}}")
    name_paragraph.style = document.styles["ResumeName"]
    name_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    build_basic_info_table(document, profile)
    document.add_paragraph("")

    # 锚点段落使用 Normal 样式且不带直接格式，插入的模块/条目完全由各自样式决定
    document.add_paragraph("{{SECTIONS}}")

    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(output))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="按参考简历生成脱敏导出模板")
    parser.add_argument("--source", help="参考简历 docx 路径（默认自动查找仓库根目录下的 docx）")
    parser.add_argument("--output", help="输出模板路径")
    args = parser.parse_args()

    source = detect_reference_path(args.source)
    profile = read_profile(source)
    output = Path(args.output) if args.output else settings.template_dir / "classic_single_column.docx"

    written = build_template(profile, source, output)
    print(f"参考简历：{source if source else '未找到，使用内置默认格式'}")
    print(f"提取格式：{profile.describe()}")
    print(f"已生成：{written}")


if __name__ == "__main__":
    main()
