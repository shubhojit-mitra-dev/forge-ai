"""Health check route."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.presentation.dependencies import ContainerDep

router = APIRouter(tags=["health"])


class HealthResponseDTO(BaseModel):
    """Liveness and dependency configuration status."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded"]
    environment: str
    litellm_configured: bool
    supabase_configured: bool


@router.get("/health", response_model=HealthResponseDTO)
async def health_check(container: ContainerDep) -> HealthResponseDTO:
    """Return service liveness and configuration readiness."""
    settings = container.settings
    litellm_ok = bool(settings.litellm_base_url)
    supabase_ok = bool(
        settings.supabase_url and (settings.supabase_service_role_key or settings.supabase_anon_key)
    )
    overall: Literal["ok", "degraded"] = "ok" if (litellm_ok and supabase_ok) else "degraded"
    return HealthResponseDTO(
        status=overall,
        environment=settings.app_env,
        litellm_configured=litellm_ok,
        supabase_configured=supabase_ok,
    )
