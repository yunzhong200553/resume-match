"""不依赖 LibreOffice 的本地 PDF 渲染兜底。"""

from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.schemas.resume_document import ResumeDocument
from app.services.export.renderer import format_item

FONT_NAME = "STSong-Light"


def render_pdf(document: ResumeDocument, *, output_path: Path) -> Path:
    """直接从 ``ResumeDocument`` 生成含中文的标准 A4 PDF。"""

    pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ResumePdfTitle",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=20,
        leading=26,
        alignment=TA_CENTER,
        textColor=HexColor("#172b4d"),
        spaceAfter=5,
    )
    contact = ParagraphStyle(
        "ResumePdfContact",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=9,
        leading=14,
        alignment=TA_CENTER,
        textColor=HexColor("#53657e"),
        spaceAfter=12,
    )
    heading = ParagraphStyle(
        "ResumePdfHeading",
        parent=styles["Heading2"],
        fontName=FONT_NAME,
        fontSize=13,
        leading=19,
        textColor=HexColor("#1f5f9e"),
        borderColor=HexColor("#9dbbd9"),
        borderPadding=(0, 0, 4),
        borderWidth=0.6,
        borderBottom=True,
        spaceBefore=8,
        spaceAfter=6,
    )
    item_title = ParagraphStyle(
        "ResumePdfItemTitle",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=10,
        leading=15,
        textColor=HexColor("#1f2e43"),
        spaceBefore=3,
    )
    content = ParagraphStyle(
        "ResumePdfContent",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=9,
        leading=15,
        leftIndent=4 * mm,
        textColor=HexColor("#3d4d62"),
        spaceAfter=3,
    )

    info = document.basic_info
    contacts = [
        value
        for value in (info.job_target, info.phone, info.email, info.location)
        if value
    ]
    story = [
        Paragraph(escape(info.name or "个人简历"), title),
        Paragraph(escape(" · ".join(contacts)), contact),
    ]
    for section in document.ordered_sections():
        if not section.items:
            continue
        story.append(Paragraph(escape(section.title), heading))
        for item in document.ordered_items(section):
            item_title_text, item_content = format_item(item, section.type)
            if item_title_text:
                story.append(Paragraph(escape(item_title_text).replace("\t", "　|　"), item_title))
            for line in item_content.splitlines():
                if line.strip():
                    story.append(Paragraph(escape(line.strip()), content))
        story.append(Spacer(1, 2 * mm))

    pdf = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=info.name or "个人简历",
    )
    pdf.build(story)
    return output_path
