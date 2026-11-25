# Architecture Decision Records (ADRs)

All architectural decisions in ForgeAI are recorded as immutable ADRs. Any deviation requires a new ADR superseding the prior decision.

| ID | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-plain-python-over-langgraph.md) | Plain Async Python + Pydantic + LiteLLM over LangChain / LangGraph | Accepted |
| [ADR-002](ADR-002-supabase-cloud-consolidation.md) | Supabase Cloud Consolidation over AWS S3 + RDS + Redis | Accepted |
| [ADR-003](ADR-003-litellm-multi-provider-routing.md) | Multi-Provider LiteLLM Routing with Gemini Primary & Groq/NIM Workers | Accepted |
| [ADR-004](ADR-004-bias-defended-custom-judge-over-ragas.md) | Custom Two-Stage Bias-Defended Judge over RAGAS | Accepted |
| [ADR-005](ADR-005-pgvector-hybrid-search.md) | `pgvector` + Postgres FTS Hybrid Search (RRF) over S3 Vectors | Accepted |
| [ADR-006](ADR-006-path-based-agent-urls.md) | Path-Based Runnable Agent URLs (`/agent/[slug]`) over Wildcard Subdomains | Accepted |
| [ADR-007](ADR-007-git-worktrees-atomic-commits.md) | Git Worktrees & Strict 1–2 File Atomic Commits | Accepted |
| [ADR-008](ADR-008-ddd-aop-backend-architecture.md) | Strict DDD Layering + AOP Cross-Cutting Decorators in `app/` | Accepted |

