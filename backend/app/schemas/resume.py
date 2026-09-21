"""简历、拆分与版本相关的请求/响应模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.schemas.resume_document import BasicInfo, ResumeDocument


class VersionSource(str, Enum):
    MANUAL = "manual"
    IMPORT = "import"
    OPTIMIZED = "optimized"


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class CreateResumeRequest(_CamelModel):
    title: str = Field(min_length=1, max_length=200)
    basic_info: BasicInfo = Field(default_factory=BasicInfo)

    @field_validator("title", mode="before")
    @classmethod
    def _strip_title(cls, value: Any) -> str:
        return str(value or "").strip()


class SaveDraftRequest(_CamelModel):
    document: ResumeDocument
    base_version_id: str | None = None


class CreateVersionRequest(_CamelModel):
    """``document`` 省略时取当前草稿内容。"""

    source: VersionSource = VersionSource.MANUAL
    base_version_id: str | None = None
    document: ResumeDocument | None = None


class ParseTextRequest(_CamelModel):
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text 不能为空")
        return value
