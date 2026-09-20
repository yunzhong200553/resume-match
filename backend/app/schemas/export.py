"""导出相关的请求/响应模型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ExportFormat(str, Enum):
    DOCX = "docx"
    PDF = "pdf"


class ExportStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ExportRequest(_CamelModel):
    template_id: str = Field(min_length=1)
    format: ExportFormat = ExportFormat.DOCX
