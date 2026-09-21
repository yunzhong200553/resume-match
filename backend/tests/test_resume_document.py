"""``ResumeDocument`` 契约测试（README 6.1）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.resume_document import ResumeDocument, SectionType, normalize_orders
from tests.fixtures import sample_document_dict


def test_document_uses_camel_case_aliases() -> None:
    document = ResumeDocument.model_validate(sample_document_dict())
    payload = document.to_storage()

    assert payload["basicInfo"]["jobTarget"] == "后端开发工程师"
    assert payload["sections"][2]["items"][0]["fields"]["startDate"] == "2026-09"
    assert "basic_info" not in payload


def test_section_type_is_restricted() -> None:
    payload = sample_document_dict()
    payload["sections"][0]["type"] = "hobby"

    with pytest.raises(ValidationError) as exc:
        ResumeDocument.model_validate(payload)

    assert "hobby" in str(exc.value)


def test_section_orders_must_start_at_zero_and_be_unique() -> None:
    payload = sample_document_dict()
    payload["sections"][1]["order"] = 0

    with pytest.raises(ValidationError):
        ResumeDocument.model_validate(payload)


def test_item_orders_must_be_contiguous() -> None:
    payload = sample_document_dict()
    item = dict(payload["sections"][2]["items"][0])
    item["id"] = "item_project_2"
    item["order"] = 2
    payload["sections"][2]["items"].append(item)

    with pytest.raises(ValidationError):
        ResumeDocument.model_validate(payload)


def test_duplicate_item_ids_are_rejected() -> None:
    payload = sample_document_dict()
    item = dict(payload["sections"][2]["items"][0])
    item["order"] = 1
    payload["sections"][2]["items"].append(item)

    with pytest.raises(ValidationError):
        ResumeDocument.model_validate(payload)


def test_unknown_fields_are_rejected() -> None:
    payload = sample_document_dict()
    payload["basicInfo"]["gender"] = "男"

    with pytest.raises(ValidationError):
        ResumeDocument.model_validate(payload)


def test_missing_title_falls_back_to_type_default() -> None:
    payload = sample_document_dict()
    payload["sections"][0]["title"] = "   "

    document = ResumeDocument.model_validate(payload)

    assert document.sections[0].title == "教育经历"


def test_normalize_orders_keeps_written_sequence() -> None:
    document = ResumeDocument.model_validate(sample_document_dict())
    # 模拟外部传入的乱序快照：仅重排列表，使 order 与书写顺序不一致
    scrambled = document.model_copy(
        update={"sections": [document.sections[2], document.sections[1], document.sections[0], document.sections[3]]}
    )

    normalized = normalize_orders(scrambled)

    assert [section.order for section in normalized.sections] == [0, 1, 2, 3]
    assert [section.id for section in normalized.sections] == [
        "section_project",
        "section_experience",
        "section_education",
        "section_skill",
    ]
    assert normalized.sections[0].items[0].order == 0
    assert normalized.ordered_sections()[0].type is SectionType.project


def test_iter_items_and_find_item() -> None:
    document = ResumeDocument.model_validate(sample_document_dict())

    pairs = document.iter_items()
    assert [item.id for _, item in pairs][:2] == ["item_education_1", "item_experience_1"]
    assert document.find_item("section_project", "item_project_1") is not None
    assert document.find_item("section_project", "item_missing") is None
