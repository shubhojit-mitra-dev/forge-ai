# ForgeAI Phased Execution Plan

Every phase is executed in an isolated **git worktree** (`git worktree add ../forge-ai-phase-<N> -b feat/phase-<N>-<slug>`), decomposed into **parallel subagent workstreams**, verified via **strict TDD + `mypy --strict` + `ruff`**, committed atomically (**1–2 files max per commit**), and tracked in `docs/progress/phase-<N>-progress.md`.

| Phase | Title | Branch | Primary Gate |
|---|---|---|---|
| [Phase 0](phase-0-foundation.md) | Environment, Tooling & Supabase Foundation | `feat/phase-0-foundation` | `uv sync`, Supabase schema + `pgvector` live, `client` build green |
| [Phase 1](phase-1-domain.md) | Pure Domain Layer (Entities, VOs, Protocols, Exceptions) | `feat/phase-1-domain` | `mypy --strict`, 0 external imports in `app/domain`, ≥90% unit cov |
| [Phase 2](phase-2-infrastructure.md) | Infrastructure Layer (LiteLLM, Supabase, Parsers, Tools, Cache) | `feat/phase-2-infrastructure` | Unit tests green + Supabase/LiteLLM smoke check |
| [Phase 3](phase-3-pipeline.md) | Application Core — ForgeAI Pipeline (Stages 1–7) | `feat/phase-3-pipeline` | End-to-end mock pipeline <2s, ≥85% cov, `mypy --strict` |
| [Phase 4](phase-4-api-cli.md) | Presentation Layer — FastAPI Routes, AOP, SSE & CLI | `feat/phase-4-api-cli` | FastAPI `TestClient` + CLI unattended smoke test |
| [Phase 5](phase-5-frontend.md) | Frontend — Next.js 16 Workspace, Live Evals & `/agent/[slug]` | `feat/phase-5-frontend` | `pnpm lint && tsc --noEmit && pnpm build` + Playwright E2E |
| [Phase 6](phase-6-demos.md) | Two Full Demo Runs & Artifact Commits | `feat/phase-6-demos` | Both demos committed in `artifacts/demos/`, all 9 reqs verified |
| [Phase 7](phase-7-deployment.md) | Production Deployment (EC2 `t3.small` + Vercel) | `feat/phase-7-deployment` | Live unattended run on `forge-ai.shubhojitmitra.com` |

