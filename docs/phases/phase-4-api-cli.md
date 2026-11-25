# Phase 4: Presentation Layer — FastAPI Routes, AOP, SSE & CLI Runner

- **Worktree:** `git worktree add ../forge-ai-phase-4 -b feat/phase-4-api-cli`
- **Progress File:** `docs/progress/phase-4-progress.md`

## Parallel Subagent Workstreams (Strict TDD)

### Subagent A — AOP Cross-Cutting Layer, Auth & Exception Handlers
- `app/presentation/aop/cached.py` (`@cached_llm_call` decorator using `CacheProtocol`)
- `app/presentation/aop/rate_limit_guard.py` (`@with_rate_limit_backoff` decorator)
- `app/presentation/aop/telemetry.py` (`@timed_operation` + structured correlation ID middleware)
- `app/presentation/middleware/auth.py` (Supabase JWT verification via `PyJWT`, `Annotated[UserContext, Depends(...)]`)
- `app/presentation/handlers/exception_handlers.py` (DomainError → RFC 7807 `ProblemDetails` JSON)

### Subagent B — Controllers, Routes, SSE & Chat Runner
- `app/application/services/chat_runner_service.py` (loads any `AgentDefinition`, runs hybrid RAG, executes ONLY `selected_tools`, enforces `OutputContract`, runs `prompt-guard`)
- `app/presentation/controllers/` + `app/presentation/routes/`:
  - `health.py`, `projects.py`, `documents.py`, `intake.py`, `forge.py` (including `GET /forge/stream` SSE), `agents.py` (including `/agents/public/{slug}/chat`)
- `app/presentation/main.py` (`create_app()` factory)
- `tests/integration/test_api_routes.py` using `FastAPI TestClient` + mocked container.

### Subagent C — Unattended CLI Runner (Requirement 8 & Unattended Review)
- `app/cli.py`:
  - `python -m app.cli forge --brief "..." --docs ./folder --out ./artifacts/out`
  - `python -m app.cli chat --agent ./artifacts/out/agent_definition.json`
- `tests/integration/test_cli.py` verifying unattended end-to-end execution.

## Verification Gate
- `make lint && make typecheck && make test-cov` passes (≥ 85%).
- CLI `forge` + `chat` smoke test passes cleanly.

