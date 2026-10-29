"""``ResumeDocument`` 公共数据契约。

解析、分析、编辑和导出都以本文件为准（README 6.1）。
字段对外使用 camelCase，与 README 的 JSON 示例保持一致。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MONTH_RE = re.compile(r"^(\d{4})[-./年](\d{1,2})(?:月)?$")


class SectionType(str, Enum):
    """模块类型；成员值与 JSON 契约取值一致（README 6.1）。"""

    education = "education"
    experience = "experience"
    project = "project"
    skill = "skill"
    award = "award"
    custom = "custom"


DEFAULT_SECTION_TITLE: dict[SectionType, str] = {
    SectionType.education: "教育经历",
    SectionType.experience: "实习经历",
    SectionType.project: "项目经历",
    SectionType.skill: "技能与工具",
    SectionType.award: "荣誉奖项",
    SectionType.custom: "自定义模块",
}


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class BasicInfo(_CamelModel):
    name: str = ""
    phone: str = ""
    email: str = ""
    location: str = ""
    job_target: str = ""

    @field_validator("name", "phone", "email", "location", "job_target", mode="before")
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        normalized = re.sub(r"[\s-]", "", value)
        if normalized and not PHONE_RE.fullmatch(normalized):
            raise ValueError("电话必须是 11 位中国大陆手机号码")
        return normalized

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        if value and not EMAIL_RE.fullmatch(value):
            raise ValueError("邮箱格式无效")
        return value.lower()

    @field_validator("location")
    @classmethod
    def _validate_location(cls, value: str) -> str:
        if value and not re.fullmatch(r"[\u4e00-\u9fff]{2,12}", value):
            raise ValueError("所在城市必须为中文城市名称")
        return value


class SectionItem(_CamelModel):
    id: str = Field(min_length=1)
    order: int = Field(ge=0)
    fields: dict[str, str] = Field(default_factory=dict)
    content: str = ""
    hidden: bool = False

    @field_validator("fields", mode="before")
    @classmethod
    def _coerce_fields(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("fields 必须是字符串键值对")
        fields = {str(key): "" if item is None else str(item).strip() for key, item in value.items()}
        for key in ("startDate", "endDate", "date"):
            if key in fields:
                fields[key] = _normalize_month(fields[key], key)
        return fields

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_content(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    def field_or_empty(self, key: str) -> str:
        return (self.fields.get(key) or "").strip()


class Section(_CamelModel):
    id: str = Field(min_length=1)
    type: SectionType
    title: str = ""
    order: int = Field(ge=0)
    items: list[SectionItem] = Field(default_factory=list)
    hidden: bool = False

    @model_validator(mode="after")
    def _validate(self) -> "Section":
        if not self.title.strip():
            object.__setattr__(self, "title", DEFAULT_SECTION_TITLE[self.type])
        _assert_orders([item.order for item in self.items], f"模块 {self.id} 的条目")
        _assert_unique_ids([item.id for item in self.items], f"模块 {self.id} 的条目 ID")
        return self


class ResumeDocument(_CamelModel):
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    sections: list[Section] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "ResumeDocument":
        _assert_orders([section.order for section in self.sections], "模块")
        _assert_unique_ids([section.id for section in self.sections], "模块 ID")
        return self

    # ---- 只读辅助方法，供导出、分析适配层与模块 B 复用 ----

    def ordered_sections(self, types: Iterable[SectionType] | None = None) -> list[Section]:
        allowed = set(types) if types is not None else None
        sections = [s for s in self.sections if allowed is None or s.type in allowed]
        return sorted(sections, key=lambda s: s.order)

    def ordered_items(self, section: Section) -> list[SectionItem]:
        return sorted(section.items, key=lambda item: item.order)

    def iter_items(self) -> list[tuple[Section, SectionItem]]:
        return [
            (section, item)
            for section in self.ordered_sections()
            for item in self.ordered_items(section)
        ]

    def find_item(self, section_id: str, item_id: str) -> tuple[Section, SectionItem] | None:
        for section in self.sections:
            if section.id != section_id:
                continue
            for item in section.items:
                if item.id == item_id:
                    return section, item
        return None

    def to_storage(self) -> dict[str, Any]:
        """持久化用的 JSON（camelCase，与对外契约一致）。"""

        return self.model_dump(by_alias=True, mode="json")

    def for_output(self) -> "ResumeDocument":
        sections = [
            section.model_copy(update={"items": [item for item in section.items if not item.hidden]})
            for section in self.ordered_sections()
            if not section.hidden
        ]
        return normalize_orders(self.model_copy(update={"sections": sections}))


def _assert_orders(orders: list[int], label: str) -> None:
    if sorted(orders) != list(range(len(orders))):
        raise ValueError(f"{label} order 必须从 0 开始、连续且不重复，当前为 {orders}")


def _assert_unique_ids(ids: list[str], label: str) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError(f"{label} ID 在同一层级内不得重复")


def _normalize_month(value: str, field_name: str) -> str:
    if not value:
        return ""
    if field_name == "endDate" and value in {"至今", "现在", "目前"}:
        return "至今"
    if field_name == "date" and re.fullmatch(r"\d{4}", value):
        return value
    match = MONTH_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"{field_name} 必须为 YYYY-MM 格式" + ("或“至今”" if field_name == "endDate" else ""))
    year, month = int(match.group(1)), int(match.group(2))
    if not 1900 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError(f"{field_name} 不是有效月份")
    return f"{year:04d}-{month:02d}"


def normalize_orders(document: ResumeDocument) -> ResumeDocument:
    """按现有书写顺序重排 order，用于草稿保存与拆分结果整理。"""

    sections = []
    for section_index, section in enumerate(document.sections):
        items = [
            item.model_copy(update={"order": item_index})
            for item_index, item in enumerate(section.items)
        ]
        sections.append(section.model_copy(update={"order": section_index, "items": items}))
    return document.model_copy(update={"sections": sections})
