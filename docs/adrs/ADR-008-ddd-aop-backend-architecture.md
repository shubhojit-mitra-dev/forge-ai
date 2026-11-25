# ADR-008: Strict DDD Layering + AOP Cross-Cutting Decorators in `app/`

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
Business logic, LLM prompt calls, Supabase persistence, and FastAPI HTTP handlers must stay decoupled so unit tests run deterministically in < 2 seconds without network calls and `mypy --strict` catches contract drift at compile time.

## Decision
Partition `app/` into four strict DDD layers (`domain`, `infrastructure`, `application`, `presentation`) with Dependency Inversion via `typing.Protocol` and Aspect-Oriented Programming (AOP) decorators (`@cached_llm_call`, `@with_rate_limit_backoff`, `@timed_operation`) in `presentation/aop/`.

## Consequences
- **Positive:** Domain layer has 0 external imports; services are 100% testable with in-memory fakes; caching/telemetry/rate-limit logic never pollutes business services.
- **Negative:** Requires discipline to map between Domain Entities (`@dataclass(slots=True)`) and Application DTOs (`BaseModel`).

