"""JD 分析、Provider 状态与建议的数据契约。"""

from __future__ import annotations

from datetime import datetime, timezone
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
        if not isinstance(value, str):
            raise ValueError("jdText 必须是字符串")
        return value.strip()


class ProviderState(_CamelModel):
    status: ProviderStatus
    attempts: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def _validate_error_fields(self) -> "ProviderState":
        if self.status is ProviderStatus.FAILED:
            if not self.error_code or not self.error_code.strip():
                raise ValueError("failed Provider 必须提供非空 errorCode")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("failed Provider 必须提供非空 errorMessage")
        elif self.error_code is not None or self.error_message is not None:
            raise ValueError("非 failed Provider 的错误字段必须为 null")
        return self


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


class ScoreProviderResult(_CamelModel):
    overall_score: int = Field(ge=0, le=100)
    score_level: ScoreLevel
    summary: NonBlankText
    score_breakdown: list[ScoreDimension]
    item_matches: list[ItemMatch]
    missing_requirements: list[MissingRequirement]

    @model_validator(mode="after")
    def _validate_score_contract(self) -> "ScoreProviderResult":
        _validate_score_contract(
            self.overall_score, self.score_level, self.score_breakdown
        )
        return self


class SuggestionCandidate(_CamelModel):
    section_id: NonBlankText
    item_id: NonBlankText
    target_field: Literal["content"]
    original: str
    suggested: NonBlankText
    reason: NonBlankText = Field(max_length=300)

    @model_validator(mode="after")
    def _suggested_differs_from_original(self) -> "SuggestionCandidate":
        if self.suggested == self.original:
            raise ValueError("suggested 不得等于 original")
        return self


class SuggestionProviderResult(_CamelModel):
    suggestions: list[SuggestionCandidate]


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

    @field_validator("edited_text", mode="before")
    @classmethod
    def _strip_edited_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("created_at", "updated_at")
    @classmethod
    def _normalize_timestamps(cls, value: datetime) -> datetime:
        return _as_utc(value)

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

    @field_validator("created_at", "updated_at", "completed_at")
    @classmethod
    def _normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None

    @model_validator(mode="after")
    def _validate_score_fields(self) -> "Analysis":
        if self.overall_score is None:
            if self.score_level is not None or self.score_breakdown:
                raise ValueError("评分不可用时 scoreLevel 必须为 null 且 scoreBreakdown 为空")
        else:
            if self.score_level is None:
                raise ValueError("评分可用时必须提供 scoreLevel")
            _validate_score_contract(
                self.overall_score, self.score_level, self.score_breakdown
            )
        return self


class CreateAnalysisResult(_CamelModel):
    id: NonBlankText
    resume_version_id: NonBlankText
    status: Literal[AnalysisStatus.PROCESSING]
    providers: ProviderStates
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _normalize_created_at(cls, value: datetime) -> datetime:
        return _as_utc(value)


def _validate_score_contract(
    overall_score: int,
    score_level: ScoreLevel,
    score_breakdown: list[ScoreDimension],
) -> None:
    expected_weights = {
        ScoreDimensionName.CORE_REQUIREMENTS: 40,
        ScoreDimensionName.EXPERIENCE_EVIDENCE: 30,
        ScoreDimensionName.SKILLS_COVERAGE: 20,
        ScoreDimensionName.PRESENTATION_QUALITY: 10,
    }
    actual_weights = {item.dimension: item.weight for item in score_breakdown}
    if actual_weights != expected_weights or len(score_breakdown) != 4:
        raise ValueError("scoreBreakdown 必须包含四个固定维度及权重")
    if sum(item.score for item in score_breakdown) != overall_score:
        raise ValueError("四维评分之和必须等于 overallScore")
    expected_level = (
        ScoreLevel.HIGH
        if overall_score >= 80
        else ScoreLevel.MEDIUM
        if overall_score >= 60
        else ScoreLevel.LOW
    )
    if score_level is not expected_level:
        raise ValueError("scoreLevel 与 overallScore 区间不一致")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)