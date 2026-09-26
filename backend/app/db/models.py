"""持久化实体。

与 README 6.2 对应：Resume、ResumeVersion、Draft、Analysis、Suggestion、ExportRecord。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.errors import AppError, ErrorCode
from app.db.base import Base


def utcnow() -> datetime:
    """统一使用不带时区信息的 UTC 时间，避免 SQLite 读写口径不一致。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat()


class Resume(Base):
    """一份简历的逻辑主体。"""

    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    versions: Mapped[list["ResumeVersion"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        order_by="ResumeVersion.version",
    )
    draft: Mapped["Draft | None"] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "createdAt": to_iso(self.created_at),
            "updatedAt": to_iso(self.updated_at),
            "latestVersion": self.versions[-1].version if self.versions else 0,
        }


class ResumeVersion(Base):
    """不可变版本快照。写入后只能新增，不能修改。"""

    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "version", name="uq_resume_version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resume_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    resume: Mapped[Resume] = relationship(back_populates="versions")

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "resumeId": self.resume_id,
            "version": self.version,
            "parentVersionId": self.parent_version_id,
            "source": self.source,
            "createdAt": to_iso(self.created_at),
        }

    def to_payload(self) -> dict[str, Any]:
        payload = self.to_summary()
        payload["document"] = self.document
        return payload


@event.listens_for(ResumeVersion, "before_update")
def _block_version_update(_mapper, _connection, _target) -> None:
    """在 ORM 层拦截对正式版本的修改，把「不可变」做成结构约束而非约定。"""

    raise AppError(
        ErrorCode.VALIDATION_ERROR,
        "正式版本不可修改，请基于草稿创建新版本。",
    )


class Draft(Base):
    """可变编辑内容，一份简历同时只有一个草稿。"""

    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resume_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    base_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    resume: Mapped[Resume] = relationship(back_populates="draft")

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "resumeId": self.resume_id,
            "baseVersionId": self.base_version_id,
            "document": self.document,
            "updatedAt": to_iso(self.updated_at),
        }


class Analysis(Base):
    """一次基于不可变简历版本的 JD 分析。"""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resume_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    item_matches: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    missing_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    provider_states: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    suggestions: Mapped[list["Suggestion"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="Suggestion.created_at",
    )


class Suggestion(Base):
    """分析产生并由用户显式处理的条目建议。"""

    __tablename__ = "suggestions"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id",
            "section_id",
            "item_id",
            "target_field",
            name="uq_suggestion_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_field: Mapped[str] = mapped_column(String(30), nullable=False)
    original: Mapped[str] = mapped_column(Text, nullable=False)
    suggested: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    analysis: Mapped[Analysis] = relationship(back_populates="suggestions")


class ExportRecord(Base):
    """一次导出任务及其产物位置。"""

    __tablename__ = "export_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resume_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_payload(self, download_url: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "resumeVersionId": self.resume_version_id,
            "templateId": self.template_id,
            "format": self.format,
            "status": self.status,
            "createdAt": to_iso(self.created_at),
            "completedAt": to_iso(self.completed_at),
        }
        if download_url:
            payload["downloadUrl"] = download_url
        if self.error_code:
            payload["error"] = {"code": self.error_code, "message": self.error_message or ""}
        return payload
