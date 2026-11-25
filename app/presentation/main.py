"""FastAPI application factory for ForgeAI."""

from __future__ import annotations

import importlib

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.domain.exceptions import (
    BudgetExceededError,
    EntityNotFoundError,
    ForgeDomainError,
    GroundabilityBlockedError,
    InvalidToolSelectionError,
    ValidationDomainError,
)
from app.presentation.routes import api_v1_router

_ERROR_STATUS_MAP: dict[type[ForgeDomainError], int] = {
    EntityNotFoundError: status.HTTP_404_NOT_FOUND,
    GroundabilityBlockedError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ValidationDomainError: status.HTTP_400_BAD_REQUEST,
    InvalidToolSelectionError: status.HTTP_400_BAD_REQUEST,
    BudgetExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
}


def _register_default_exception_handlers(app: FastAPI) -> None:
    """Register RFC 7807 ProblemDetails handler for ForgeDomainError subclasses."""

    @app.exception_handler(ForgeDomainError)
    async def domain_error_handler(request: Request, exc: ForgeDomainError) -> JSONResponse:
        status_code = _ERROR_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(
            status_code=status_code,
            media_type="application/problem+json",
            content={
                "type": f"https://forgeai.dev/errors/{exc.code.lower()}",
                "title": exc.__class__.__name__,
                "status": status_code,
                "detail": exc.detail,
                "code": exc.code,
                "instance": str(request.url.path),
            },
        )


def _wire_optional_subagent_extensions(app: FastAPI) -> None:
    """Attach Subagent 4A exception handlers and telemetry middleware when available."""
    handlers_registered = False
    try:
        exc_mod = importlib.import_module("app.presentation.handlers.exception_handlers")
        register_fn = getattr(exc_mod, "register_exception_handlers", None)
        if callable(register_fn):
            register_fn(app)
            handlers_registered = True
    except ModuleNotFoundError:
        pass

    if not handlers_registered:
        _register_default_exception_handlers(app)

    try:
        telemetry_mod = importlib.import_module("app.presentation.aop.telemetry")
        middleware_cls = getattr(telemetry_mod, "TelemetryMiddleware", None)
        if middleware_cls is not None:
            app.add_middleware(middleware_cls)
    except ModuleNotFoundError:
        pass


def create_app() -> FastAPI:
    """Create and configure the ForgeAI FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="ForgeAI API",
        version="0.1.0",
        description="ForgeAI: The Agent That Builds Agents",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _wire_optional_subagent_extensions(app)
    app.include_router(api_v1_router)
    return app


app = create_app()
