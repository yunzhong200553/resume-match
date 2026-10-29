"""Named job layout save contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.schemas.resume_document import ResumeDocument


class SaveLayoutRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    jd_text: str = Field(default="", max_length=20_000)
    document: ResumeDocument
    analysis_id: str | None = None

    @field_validator("name", "jd_text", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class UpdateLayoutRequest(SaveLayoutRequest):
    expected_updated_at: datetime
