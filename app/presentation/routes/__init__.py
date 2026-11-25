"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.presentation.routes.agents import router as agents_router
from app.presentation.routes.documents import router as documents_router
from app.presentation.routes.forge import router as forge_router
from app.presentation.routes.health import router as health_router
from app.presentation.routes.intake import router as intake_router
from app.presentation.routes.projects import router as projects_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(intake_router)
api_v1_router.include_router(forge_router)
api_v1_router.include_router(agents_router)

__all__ = ["api_v1_router"]
