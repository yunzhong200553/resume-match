"""Named job layout persistence and export."""

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.response import envelope
from app.schemas.export import ExportRequest
from app.schemas.layout import SaveLayoutRequest, UpdateLayoutRequest
from app.schemas.resume import VersionSource
from app.schemas.resume_document import ResumeDocument
from app.services import layout_service, version_service
from app.services.export import export_service

router = APIRouter(tags=["岗位排版"])


@router.get("/resumes/{resume_id}/layouts")
def list_layouts(resume_id: str, db: DbSession) -> dict[str, Any]:
    return envelope({"items": [layout.to_payload(include_document=False) for layout in layout_service.list_layouts(db, resume_id)]})


@router.post("/resumes/{resume_id}/layouts", status_code=201)
def create_layout(resume_id: str, payload: SaveLayoutRequest, db: DbSession) -> dict[str, Any]:
    return envelope(layout_service.save_layout(db, resume_id, payload).to_payload())


@router.get("/resume-layouts/{layout_id}")
def get_layout(layout_id: str, db: DbSession) -> dict[str, Any]:
    return envelope(layout_service.get_layout(db, layout_id).to_payload())


@router.put("/resume-layouts/{layout_id}")
def update_layout(layout_id: str, payload: UpdateLayoutRequest, db: DbSession) -> dict[str, Any]:
    layout = layout_service.get_layout(db, layout_id)
    return envelope(layout_service.save_layout(
        db, layout.resume_id, payload, layout_id=layout_id, expected_updated_at=payload.expected_updated_at,
    ).to_payload())


@router.post("/resume-layouts/{layout_id}/exports", status_code=201)
def export_layout(layout_id: str, payload: ExportRequest, db: DbSession) -> dict[str, Any]:
    layout = layout_service.get_layout(db, layout_id)
    version = version_service.create_version(
        db, resume_id=layout.resume_id, source=VersionSource.OPTIMIZED,
        document=ResumeDocument.model_validate(layout.document),
    )
    record = export_service.create_export(
        db, version_id=version.id, template_id=payload.template_id,
        export_format=payload.format, layout_id=layout.id,
    )
    return envelope(export_service.export_payload(record))
