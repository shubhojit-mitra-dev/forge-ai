# Phase 0: Environment, Tooling & Supabase Foundation

- **Worktree:** `git worktree add ../forge-ai-phase-0 -b feat/phase-0-foundation`
- **Progress File:** `docs/progress/phase-0-progress.md`

## Parallel Subagent Workstreams

### Subagent A — Python Backend & Tooling Verification
- Run `uv sync --all-extras` to lock all backend + dev dependencies (`fastapi`, `litellm`, `supabase`, `pdfplumber`, `pandas`, `mypy`, `ruff`, `pytest`).
- Create package `__init__.py` skeletons under `app/domain/`, `app/infrastructure/`, `app/application/`, `app/presentation/`, and `tests/unit/`, `tests/integration/`.
- Add `tests/unit/test_smoke.py` verifying Python 3.12+ and config settings loading.

### Subagent B — Supabase Schema & Storage Provisioning (via Supabase MCP)
- Enable `vector` extension (`CREATE EXTENSION IF NOT EXISTS vector;`).
- Apply SQL migration creating: `forge_projects`, `documents`, `document_chunks` (`vector(768)` + HNSW index + `tsvector` GIN index), `agent_definitions`, `eval_cases`, `eval_runs`, `eval_results`, `iteration_logs`, `conversations`, `messages`.
- Create `match_document_chunks_hybrid` RPC function implementing Reciprocal Rank Fusion (RRF) over cosine similarity + FTS.
- Configure Row Level Security (RLS) policies on all tables + public read policy for published `agent_definitions`.
- Create private storage bucket `forge-documents`.

### Subagent C — Frontend (`client/`) Baseline & Dependencies
- Read `client/AGENTS.md` and `client/DESIGN.md`.
- Install `@supabase/ssr`, `@supabase/supabase-js`, `zod`, `lucide-react`, and initialize `shadcn/ui` primitives (`button`, `card`, `badge`, `tabs`, `sheet`, `scroll-area`, `tooltip`, `sonner`).
- Configure Anthropic Design System tokens from `client/DESIGN.md` into `client/app/globals.css`.

## Verification Gate
1. `make lint && make typecheck && make test-unit` passes with 0 errors.
2. Supabase tables, `match_document_chunks_hybrid` RPC, and `forge-documents` bucket verified via Supabase MCP.
3. `cd client && pnpm lint && pnpm exec tsc --noEmit && pnpm build` passes.

