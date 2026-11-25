# ForgeAI — The Agent That Builds Agents

ForgeAI is an unattended, honest **Agent Factory** built on Python 3.12+, FastAPI, LiteLLM, Supabase (`pgvector` + Auth + Storage + Realtime), and Next.js 16. Given a one-paragraph brief and a folder of documents, ForgeAI interviews the requester (≤5 questions), runs a Groundability Guard, synthesizes a declarative `AgentDefinition` with strict tool-selection discipline, auto-generates ≥20 evaluation cases from the documents, scores them with a cross-model bias-defended Judge, runs a targeted Critic–Optimizer loop (≤3 iterations), and emits an honest quality report alongside a runnable chat interface.

## Architecture & Documentation
- [AGENTS.md](AGENTS.md) — Engineering constitution, DDD/TDD rules, atomic commit policy
- [docs/architecture.md](docs/architecture.md) — System topology, DDD layout, Supabase schema, 3-layer caching
- [docs/contracts.md](docs/contracts.md) — Pydantic v2 DTOs, Tool Protocol, `/api/v1` API contracts
- [docs/eval-and-judge-spec.md](docs/eval-and-judge-spec.md) — Groundability Guard, bias-defended Judge, Critic–Optimizer loop
- [docs/adrs/README.md](docs/adrs/README.md) — Architecture Decision Records (`ADR-001`–`ADR-008`)
- [docs/slas/README.md](docs/slas/README.md) — Rate-limit budgets, SLOs, and circuit breakers

## Quickstart (Local Development & Unattended CLI)

```bash
# 1. Install backend & frontend dependencies
make install

# 2. Run static checks & test suite (209 tests, >=85% coverage)
make lint && make typecheck && make test-cov

# 3. Run ForgeAI unattended on any unseen brief & document folder
uv run python -m app.cli forge \
  --brief path/to/brief.txt \
  --docs path/to/docs_folder \
  --out ./artifacts/run-1 \
  --non-interactive

# 4. Chat with any generated AgentDefinition
uv run python -m app.cli chat \
  --agent ./artifacts/run-1/agent_definition.json \
  --docs path/to/docs_folder
```

## Two Committed Demo Runs
- **Demo 1 (HR Policy Assistant):** [artifacts/demos/hr-policy/](artifacts/demos/hr-policy/) — `selected_tools: []` (excludes `weather_http` and `csv_lookup`), 2 iterations, [honest_report.md](artifacts/demos/hr-policy/honest_report.md).
- **Demo 2 (Ship-Spares Procurement Assistant):** [artifacts/demos/ship-spares/](artifacts/demos/ship-spares/) — `selected_tools: ["csv_lookup", "calculator", "current_date"]` (excludes `weather_http`), [honest_report.md](artifacts/demos/ship-spares/honest_report.md).

## Deployment (EC2 `t3.small` + Vercel)
- **Backend (`docker-compose.yml` + `Caddyfile`):** `docker compose up -d` on EC2 `t3.small` serving FastAPI (`:8000`) + LiteLLM (`:4000`).
- **Frontend (`client/`):** Deploy `client/` on Vercel (`forge-ai.shubhojitmitra.com`) with `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_API_URL`.
