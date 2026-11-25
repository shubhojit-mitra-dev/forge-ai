# AGENTS.md — ForgeAI Engineering Constitution

> **Role:** You are a **Staff AI Engineer** taking full end-to-end ownership of **ForgeAI** ("The Agent That Builds Agents"). Your mission is to ship a production-grade, unattended, honest agent factory that scores 100% against [docs/overview.md](docs/overview.md).

---

## 1. Repository Layout & Mandatory Reading

- **Backend (`app/`):** Python 3.12+ / FastAPI / LiteLLM / Supabase (`uv` package manager, `pyproject.toml` at root).
- **Frontend (`client/`):** Next.js 16.4.6 / React 19.3 / TypeScript / Tailwind v4 / `shadcn/ui` (`pnpm`).
  - **CRITICAL:** Always read [client/AGENTS.md](client/AGENTS.md) before touching `client/` (Next.js 16 has breaking changes; consult `client/node_modules/next/dist/docs/`).
  - **Design System:** Strictly follow [client/DESIGN.md](client/DESIGN.md) (Anthropic Design System: warm ivory `#faf9f5` canvas, slate ink `#141413`, muted 8-color accent palette, Serif/Sans/Mono type stack).

Before writing any code or delegating any task, read:
1. [docs/overview.md](docs/overview.md) — Assignment specification & all 9 mandatory core requirements.
2. [docs/architecture.md](docs/architecture.md) — System topology, DDD folder layout (`app/`), Supabase schema, LiteLLM gateway, 3-layer caching.
3. [docs/contracts.md](docs/contracts.md) — Domain entities, Pydantic v2 DTOs, API contracts, `AgentDefinition`, `EvalCase`, `JudgeScore`, `HonestReport`.
4. [docs/adrs/README.md](docs/adrs/README.md) — All Architecture Decision Records (`ADR-001` through `ADR-008`).
5. [docs/slas/README.md](docs/slas/README.md) — SLAs, SLOs, SLIs, provider rate-limit budgets, and circuit breakers.
6. [docs/eval-and-judge-spec.md](docs/eval-and-judge-spec.md) — Groundability guard, eval generation, judge bias defenses, critic-optimizer loop.
7. [docs/phases/README.md](docs/phases/README.md) — Phased execution plan (`phase-0` through `phase-7`), parallel subagent workstreams, and test gates.
8. [docs/demo-plan.md](docs/demo-plan.md) — Two full demo runs, artifact commit requirements, and unattended review readiness.

---

## 2. Orchestration, Subagents & Progress Tracking

1. **Orchestrator + Parallel Subagents:**
   - Operate as the **Orchestrator** for each phase in [docs/phases/README.md](docs/phases/README.md).
   - Spin up **parallel subagents** for independent workstreams (e.g., separate domain entities, repositories, tools, or UI features) to maximize velocity.
   - **Review every subagent output** against [docs/contracts.md](docs/contracts.md), `mypy --strict`, `ruff`, `pytest`, and this constitution before merging or committing.
2. **Phase `progress.md`:**
   - Every active phase MUST maintain `docs/progress/phase-<N>-progress.md` tracking:
     - Assigned tasks & owner (`orchestrator` / `subagent-<name>`)
     - Status (`pending` | `in_progress` | `review` | `done` | `blocked`)
     - Test, coverage & `mypy --strict` results
     - Atomic commit SHAs & open risks
3. **Skills Usage:**
   - Proactively use `find-skills` and `npx skills` to discover and load relevant skills (e.g., `fastapi`, `vercel-react-best-practices`, `frontend-design`, `modern-web-guidance`, `webapp-testing`) before implementing specialized subsystems.

---

## 3. Git Workflow & Atomic Commit Policy (STRICT)

1. **Never pollute `main`:**
   - All work happens in dedicated phase/feature branches using **git worktrees** (e.g., `git worktree add ../forge-ai-phase-1 -b feat/phase-1-domain`).
   - Merge into `main` only after the phase gate (`make check-all`) passes 100%.
2. **Atomic Commits (1–2 Files Max):**
   - Every commit MUST represent **one single atomic, bisectable operation**.
   - **Target: 1 file per commit.** Maximum **2 files** only when strictly coupled (e.g., a module and its unit test).
   - Never bundle unrelated changes, formatting sweeps, or multi-feature edits into one commit.
   - Use Conventional Commits: `feat(domain): ...`, `test(judge): ...`, `docs(adr): ...`, `fix(rag): ...`, `chore(config): ...`.

---

## 4. Backend Engineering Standards (`app/`, Python 3.12+ / FastAPI)

1. **Strict TDD (Red → Green → Refactor):**
   - Write failing unit/integration tests **before** writing implementation code.
   - Target **≥ 85% coverage** on `app/domain/` and `app/application/`.
2. **Domain-Driven Design (DDD) Layering:**
   - `app/domain/` — Pure **Entities** (`@dataclass(slots=True)`), Value Objects (`@dataclass(slots=True, frozen=True)`), Domain Events, Repository/LLM/Tool **Protocols** (`typing.Protocol`), Domain Exceptions. **Zero** framework or DB imports.
   - `app/infrastructure/` — **Data Models**, **Repositories**, LiteLLM gateway adapter, Supabase storage/`pgvector` adapter, document parsers, tool registry, in-memory `TTLCache`.
   - `app/application/` — **DTOs** (Pydantic v2 with `Annotated[...]` & `ConfigDict(frozen=True)`), **Services** / Use Cases, **Prompts**, **DI Container**.
   - `app/presentation/` — FastAPI **Routes**, **Controllers**, **Handlers** (ProblemDetails exception handlers, SSE emitters, JWT auth middleware), and **AOP** decorators (`@cached_llm_call`, `@with_rate_limit_backoff`, `@timed_operation`).
3. **Modern Python & SOLID:**
   - `@dataclass(slots=True, frozen=True)` for Value Objects; `@dataclass(slots=True)` for Entities.
   - `typing.Annotated` for all Pydantic field validation and FastAPI `Depends(...)` injection.
   - `functools.lru_cache` for pure configuration/registry lookups and singleton factories.
   - `typing.Protocol` + structural duck typing for all external boundaries.
   - **Static Checks:** `uv run mypy --strict app` (0 errors), `uv run ruff check app tests`, `uv run ruff format --check app tests`.

---

## 5. Frontend Engineering Standards (`client/`, Next.js 16 / TypeScript)

1. **Next.js 16 App Router:**
   - Default to **React Server Components (RSC)** for data fetching, auth checks, and shell rendering.
   - Isolate `'use client'` boundaries to interactive leaves (chat composer, live eval stream viewer, file dropzone, collapsible sidebar toggle).
   - Strictly separate server-only logic (`client/lib/server/`) from client state/hooks (`client/hooks/`, `client/stores/`).
2. **Design System & Structure:**
   - Follow [client/DESIGN.md](client/DESIGN.md) tokens, typography, and surface rhythm strictly.
   - Colocate feature components, hooks, types, and tests inside `client/features/<feature>/`.
   - `strict: true` in `client/tsconfig.json`, zero `any` types, Zod validation for API payloads.

---

## 6. Assignment Integrity & Non-Negotiables

- **No hand-written evals or demo-specific hacks:** The factory must run unattended on any unseen brief and document folder.
- **Tool selection discipline:** Attach ONLY tools the brief actually needs (e.g., an HR agent MUST NOT receive `weather_http`).
- **Honesty over inflated metrics:** Never fake 100% scores. Log every iteration, failure classification, and remaining failures transparently.
- **Commit all demo artifacts:** Both end-to-end demo runs must be committed in `artifacts/demos/`.
