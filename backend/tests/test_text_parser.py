"""拆分规则单元测试：完整 / 缺失模块 / 乱序 / 重复标题 / 长文本。"""

from __future__ import annotations

import pytest

from app.schemas.resume_document import SectionType
from app.services.parsing.docx_extractor import extract_text as extract_docx_text
from app.services.parsing.text_parser import parse_resume_text
from tests.fixtures import (
    SAMPLE_TEXT,
    THREE_LINE_STYLE_TEXT,
    find_reference_resume,
    long_resume_text,
    write_reference_style_docx,
)


def _section(document, section_type: SectionType):
    return next(section for section in document.sections if section.type is section_type)


def test_complete_resume_is_structured() -> None:
    outcome = parse_resume_text(SAMPLE_TEXT)
    document = outcome.document

    assert document.basic_info.name == "李小明"
    assert document.basic_info.phone == "13800000000"
    assert document.basic_info.email == "lixiaoming@example.com"
    assert document.basic_info.location == "杭州"
    assert document.basic_info.job_target == "后端开发工程师"

    assert [section.type for section in document.sections] == [
        SectionType.education,
        SectionType.experience,
        SectionType.project,
        SectionType.skill,
    ]

    education = _section(document, SectionType.education).items[0]
    assert education.fields == {
        "school": "浙江大学",
        "major": "计算机科学与技术",
        "degree": "本科",
        "startDate": "2019-09",
        "endDate": "2023-06",
    }

    experience = _section(document, SectionType.experience).items[0]
    assert experience.fields["company"] == "杭州云帆科技有限公司"
    assert experience.fields["role"] == "后端开发实习生"
    assert experience.fields["startDate"] == "2024-07"
    assert "订单系统重构" in experience.content
    assert "FastAPI" in experience.content
    # 项目符号标记不会残留在正文里
    assert not experience.content.startswith(("-", "•", "·"))

    project = _section(document, SectionType.project).items[0]
    assert project.fields["name"] == "ResumeMatch"
    assert project.fields["role"] == "后端开发"
    assert "项目背景" in project.content
    assert "成果" in project.content

    skills = _section(document, SectionType.skill).items
    assert [item.fields["category"] for item in skills] == ["编程", "AI工具", "协作工具"]
    assert skills[0].content == "Python，Java，Git"
    assert skills[2].content == "腾讯文档"


def test_three_line_style_headers_are_grouped() -> None:
    outcome = parse_resume_text(THREE_LINE_STYLE_TEXT)
    document = outcome.document

    assert document.basic_info.name == "王小花"
    assert document.basic_info.phone == "13900000000"

    education = _section(document, SectionType.education)
    assert len(education.items) == 1
    assert education.items[0].fields == {
        "school": "上海交通大学",
        "major": "软件工程",
        "degree": "硕士",
        "startDate": "2023-09",
        "endDate": "至今",
    }

    experience = _section(document, SectionType.experience)
    assert len(experience.items) == 1
    assert experience.items[0].fields["company"] == "某互联网公司"
    assert experience.items[0].fields["role"] == "后端开发实习生"
    assert "参与推荐服务开发" in experience.items[0].content
    # 日期行不会被当成条目正文
    assert "2024.07" not in experience.items[0].content


def test_multiple_items_in_one_section() -> None:
    text = (
        "姓名：赵六\n"
        "项目经历\n"
        "项目甲 | 后端开发 | 2024.01 - 2024.06\n"
        "项目内容：完成甲。\n"
        "项目乙 | 前端开发 | 2024.07 - 2024.12\n"
        "项目内容：完成乙。"
    )

    outcome = parse_resume_text(text)
    items = _section(outcome.document, SectionType.project).items

    assert [item.fields["name"] for item in items] == ["项目甲", "项目乙"]
    assert items[0].fields["endDate"] == "2024-06"
    assert items[1].content == "项目内容：完成乙。"


def test_bullet_only_section_splits_per_bullet() -> None:
    text = "姓名：钱七\n荣誉奖项\n- 校级一等奖学金 2024\n- 全国大学生数学建模竞赛二等奖 2023"

    outcome = parse_resume_text(text)
    items = _section(outcome.document, SectionType.award).items

    assert len(items) == 2
    assert items[0].fields["name"] == "校级一等奖学金"
    assert items[0].fields["date"] == "2024"


def test_missing_modules_are_tolerated() -> None:
    text = "姓名：孙八\n教育背景\n北京大学 | 法学 | 本科 | 2018.09 - 2022.06"

    outcome = parse_resume_text(text)

    assert len(outcome.document.sections) == 1
    assert outcome.document.sections[0].type is SectionType.education
    assert outcome.document.sections[0].items[0].fields["school"] == "北京大学"


def test_shuffled_modules_keep_original_order() -> None:
    text = (
        "姓名：周九\n"
        "技能与工具\n编程：Python，SQL；\n"
        "项目经历\n简历匹配系统 | 后端开发 | 2025.01 - 2025.06\n- 完成接口开发。\n"
        "教育背景\n同济大学 | 软件工程 | 本科 | 2019.09 - 2023.06"
    )

    outcome = parse_resume_text(text)

    assert [section.type for section in outcome.document.sections] == [
        SectionType.skill,
        SectionType.project,
        SectionType.education,
    ]
    assert [section.order for section in outcome.document.sections] == [0, 1, 2]


def test_duplicate_titles_are_kept_as_separate_sections_with_warning() -> None:
    text = (
        "姓名：吴十\n"
        "项目经历\n项目甲 | 后端开发 | 2024.01 - 2024.06\n- 完成甲。\n"
        "项目经历\n项目乙 | 前端开发 | 2024.07 - 2024.12\n- 完成乙。"
    )

    outcome = parse_resume_text(text)
    sections = outcome.document.sections

    assert len(sections) == 2
    assert [section.id for section in sections] == ["section_project", "section_project_2"]
    assert any("重复的模块标题" in warning for warning in outcome.warnings)


def test_custom_section_is_recognized() -> None:
    text = "姓名：郑十一\n【自我评价】\n具备良好的团队协作能力。"

    outcome = parse_resume_text(text)
    sections = outcome.document.sections

    assert len(sections) == 1
    assert sections[0].type is SectionType.custom
    assert sections[0].title == "自我评价"


def test_personal_info_heading_is_not_a_section() -> None:
    text = "个人信息\n姓名：冯十二\n手机：13600000000\n教育背景\n南京大学 | 计算机 | 本科 | 2019.09 - 2023.06"

    outcome = parse_resume_text(text)

    assert outcome.document.basic_info.name == "冯十二"
    assert outcome.document.basic_info.phone == "13600000000"
    assert [section.type for section in outcome.document.sections] == [SectionType.education]


def test_contract_foreign_labels_are_reported() -> None:
    text = "姓名：陈十三\n性别：男\n出生年月：2000/01/01\n教育背景\n某大学 | 计算机 | 本科 | 2019.09 - 2023.06"

    outcome = parse_resume_text(text)

    assert any("性别" in warning and "出生年月" in warning for warning in outcome.warnings)


def test_text_without_modules_returns_warning() -> None:
    outcome = parse_resume_text("这是一段没有任何模块标题的纯文本。")

    assert outcome.document.sections == []
    assert any("未能识别出任何简历模块" in warning for warning in outcome.warnings)


def test_missing_date_produces_warning() -> None:
    outcome = parse_resume_text("姓名：褚十四\n项目经历\n某项目\n- 缺少日期区间。")

    assert any("未识别到日期区间" in warning for warning in outcome.warnings)


def test_long_resume_keeps_all_items() -> None:
    text = long_resume_text(repeat=120)

    outcome = parse_resume_text(text)
    document = outcome.document
    counts = {section.type: len(section.items) for section in document.sections}

    assert outcome.source_text_length == len(text)
    assert counts[SectionType.experience] == 120
    assert counts[SectionType.project] == 120
    assert counts[SectionType.skill] == 1
    for section in document.sections:
        assert [item.order for item in section.items] == list(range(len(section.items)))


def test_docx_extractor_matches_text_parser(tmp_path) -> None:
    """参考简历的表格排版经 DOCX 提取后，仍能拆出同样的结构。"""

    docx_path = write_reference_style_docx(tmp_path / "sample.docx")

    text = extract_docx_text(docx_path)
    outcome = parse_resume_text(text)
    document = outcome.document

    assert document.basic_info.name == "李小明"
    assert document.basic_info.phone == "13800000000"
    assert document.basic_info.location == "杭州"
    assert [section.type for section in document.sections] == [
        SectionType.education,
        SectionType.experience,
        SectionType.project,
        SectionType.skill,
    ]
    assert _section(document, SectionType.experience).items[0].fields["company"] == "杭州云帆科技有限公司"
    assert "订单系统重构" in _section(document, SectionType.experience).items[0].content


def test_reference_resume_can_be_parsed(repo_root) -> None:
    """本机存在参考简历时校验其可被拆分为非空结构（不校验具体个人信息）。"""

    reference = find_reference_resume(repo_root)
    if reference is None:
        pytest.skip("仓库根目录没有参考简历 docx，跳过")

    text = extract_docx_text(reference)
    outcome = parse_resume_text(text)
    document = outcome.document

    assert document.basic_info.phone
    assert document.basic_info.email
    assert len(document.sections) >= 3
    for section in document.sections:
        assert section.items, f"模块 {section.title} 未拆出任何条目"

    project = next(
        (section for section in document.sections if section.type is SectionType.project), None
    )
    assert project is not None
    assert all(item.fields.get("startDate") for item in project.items)
    assert all("|" not in (item.content or "") for item in project.items)
