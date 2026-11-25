"""Global FastAPI exception handlers mapping domain errors to RFC 7807 ProblemDetails."""

from typing import Annotated

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.domain.exceptions import (
    BudgetExceededError,
    EntityNotFoundError,
    ForgeDomainError,
    GroundabilityBlockedError,
    InvalidToolSelectionError,
    ValidationDomainError,
)


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details JSON response payload."""

    model_config = ConfigDict(frozen=True)

    type: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    status: Annotated[int, Field(ge=400, le=599)]
    detail: Annotated[str, Field(min_length=1)]
    code: Annotated[str, Field(min_length=1)]


_DOMAIN_ERROR_STATUS_MAP: tuple[tuple[type[ForgeDomainError], int, str], ...] = (
    (EntityNotFoundError, status.HTTP_404_NOT_FOUND, "Entity Not Found"),
    (GroundabilityBlockedError, status.HTTP_422_UNPROCESSABLE_CONTENT, "Groundability Blocked"),
    (BudgetExceededError, status.HTTP_429_TOO_MANY_REQUESTS, "Budget Exceeded"),
    (InvalidToolSelectionError, status.HTTP_400_BAD_REQUEST, "Invalid Tool Selection"),
    (ValidationDomainError, status.HTTP_400_BAD_REQUEST, "Validation Error"),
)


def _resolve_status_and_title(exc: ForgeDomainError) -> tuple[int, str]:
    for exc_type, http_status, title in _DOMAIN_ERROR_STATUS_MAP:
        if isinstance(exc, exc_type):
            return http_status, title
    return status.HTTP_400_BAD_REQUEST, "Domain Error"


async def domain_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Convert any ForgeDomainError into an RFC 7807 application/problem+json response."""
    domain_exc = exc if isinstance(exc, ForgeDomainError) else ForgeDomainError("ERROR", str(exc))
    http_status, title = _resolve_status_and_title(domain_exc)
    problem = ProblemDetails(
        type=f"urn:forgeai:error:{domain_exc.code}",
        title=title,
        status=http_status,
        detail=domain_exc.detail,
        code=domain_exc.code,
    )
    return JSONResponse(
        status_code=http_status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register ForgeAI domain exception handlers on a FastAPI application."""
    app.add_exception_handler(ForgeDomainError, domain_exception_handler)
