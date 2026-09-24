"""JD 分析、Provider 状态与建议的数据契约。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AnalysisStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class ScoreLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RequirementImportance(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class SuggestionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"


class ProviderStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ScoreDimensionName(str, Enum):
    CORE_REQUIREMENTS = "coreRequirements"
    EXPERIENCE_EVIDENCE = "experienceEvidence"
    SKILLS_COVERAGE = "skillsCoverage"
    PRESENTATION_QUALITY = "presentationQuality"


class CreateAnalysisRequest(_CamelModel):
    resume_version_id: NonBlankText
    jd_text: str

    @field_validator("jd_text", mode="before")
    @classmethod
    def _strip_jd_text(cls, value: Any) -> str:
        return str(value or "").strip()


class ProviderState(_CamelModel):
    status: ProviderStatus
    attempts: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None


class ProviderStates(_CamelModel):
    score_agent: ProviderState
    suggestion_agent: ProviderState


class ScoreDimension(_CamelModel):
    dimension: ScoreDimensionName
    weight: int = Field(gt=0, le=100)
    score: int = Field(ge=0)
    reason: NonBlankText

    @model_validator(mode="after")
    def _score_within_weight(self) -> "ScoreDimension":
        if self.score > self.weight:
            raise ValueError("score 不得超过 weight")
        return self


class ItemMatch(_CamelModel):
    section_id: NonBlankText
    item_id: NonBlankText
    level: MatchLevel
    matched_requirements: list[NonBlankText]
    reason: NonBlankText = Field(max_length=300)


class MissingRequirement(_CamelModel):
    requirement: NonBlankText
    importance: RequirementImportance
    reason: NonBlankText


class Suggestion(_CamelModel):
    id: NonBlankText
    analysis_id: NonBlankText
    section_id: NonBlankText
    item_id: NonBlankText
    target_field: Literal["content"]
    original: str
    suggested: NonBlankText
    reason: NonBlankText = Field(max_length=300)
    status: SuggestionStatus
    edited_text: str | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate_texts(self) -> "Suggestion":
        if self.suggested == self.original:
            raise ValueError("suggested 不得等于 original")
        if self.status is SuggestionStatus.EDITED:
            if self.edited_text is None or not self.edited_text.strip():
                raise ValueError("edited 状态必须提供非空 editedText")
        elif self.edited_text is not None:
            raise ValueError("非 edited 状态的 editedText 必须为 null")
        return self


class Analysis(_CamelModel):
    id: NonBlankText
    resume_version_id: NonBlankText
    status: AnalysisStatus
    jd_text: str
    overall_score: int | None = Field(default=None, ge=0, le=100)
    score_level: ScoreLevel | None = None
    summary: str | None = None
    score_breakdown: list[ScoreDimension] = Field(default_factory=list)
    item_matches: list[ItemMatch] = Field(default_factory=list)
    missing_requirements: list[MissingRequirement] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    providers: ProviderStates
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class CreateAnalysisResult(_CamelModel):
    id: NonBlankText
    resume_version_id: NonBlankText
    status: Literal[AnalysisStatus.PROCESSING]
    providers: ProviderStates
    created_at: datetime