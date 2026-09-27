"""路由聚合。"""

from fastapi import APIRouter

from app.api.routes import analyses, exports, resume_versions, resumes, suggestions

api_router = APIRouter()
api_router.include_router(analyses.router)
api_router.include_router(suggestions.router)
api_router.include_router(resumes.router)
api_router.include_router(resume_versions.router)
api_router.include_router(exports.router)

__all__ = ["api_router"]
