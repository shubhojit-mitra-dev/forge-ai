# ForgeAI System Architecture

## 1. High-Level Topology

ForgeAI is an unattended **Agent Factory** ("The Agent That Builds Agents") paired with a **Generic Agent Chat Runner** and **Live Eval Observability**.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Vercel (Frontend - Next.js 15)                   │
│  • App Router (RSC by default) + shadcn/ui + Tailwind CSS               │
│  • Collapsible conversation sidebar + Chat Builder UI                   │
│  • Live Eval Observability panel (Supabase Realtime / SSE)              │
│  • Standalone Runnable Agent Route: /agent/[agent_slug]                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS (JWT Bearer via Supabase Auth)
┌───────────────────────────────▼─────────────────────────────────────────┐
│                    AWS EC2 t3.small (2 vCPU, 2 GB RAM)                  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  FastAPI Backend (:8000) — Strict DDD + AOP                       │  │
│  │  • /api/v1/forge/*    (Intake, Groundability, Build, Eval Loop)   │  │
│  │  • /api/v1/agents/*   (CRUD, Definitions, Export Artifacts)       │  │
│  │  • /api/v1/chat/*     (Generic Runnable Agent + RAG + Tools)      │  │
│  │  • /api/v1/docs/*     (Upload, Parse, Chunk, Embed)               │  │
│  │  • In-memory TTLCache (Prompt cache + Eval cache)                 │  │
│  └────────────────────────────┬──────────────────────────────────────┘  │
│                               │ OpenAI-compatible HTTP                  │
│  ┌────────────────────────────▼──────────────────────────────────────┐  │
│  │  LiteLLM Proxy Sidecar (:4000)                                    │  │
│  │  • Primary Orchestrator : Gemini 2.5 Flash-Lite (high RPD/TPM)    │  │
│  │  • Generation / Judge   : Groq (gpt-oss-120b, gpt-oss-20b, qwen)  │  │
│  │  • Quality Escalation   : NVIDIA NIM (Nemotron 3.5 / Ultra)       │  │
│  │  • Embeddings / Guard   : Cloudflare Workers AI + Groq PromptGuard│  │
│  └───────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                          Supabase Cloud                                 │
│  • Auth      : Email/OAuth JWT + Row Level Security (RLS)               │
│  • Storage   : Private bucket `forge-documents` (PDF, CSV, MD, TXT)     │
│  • Postgres  : Projects, Requirements, Agents, Evals, Logs, Chats       │
│  • pgvector  : `document_chunks` table with HNSW/IVFFlat cosine index   │
│  • Realtime  : Broadcast/Postgres Changes for live eval iteration UI    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Backend DDD Folder Structure (`app/`)

`app/` strictly separates Domain, Infrastructure, Application, and Presentation (`pyproject.toml`, `mypy.ini`, `ruff.toml`, `pytest.ini` live at repo root):

```text
app/
├── __init__.py
├── cli.py                               # Unattended CLI runner (`forge` & `chat`)
├── config.py                            # Pydantic Settings + @lru_cache
│
├── domain/                              # ZERO framework/DB imports
│   │   ├── entities/
│   │   │   ├── project.py               # ForgeProject (@dataclass(slots=True))
│   │   │   ├── document.py              # Document, DocumentChunk
│   │   │   ├── requirements.py          # RequirementsDoc, GroundabilityReport
│   │   │   ├── agent_definition.py      # AgentDefinition, RetrievalConfig, OutputContract
│   │   │   ├── evaluation.py            # EvalCase, JudgeScore, IterationLog, HonestReport
│   │   │   └── conversation.py          # Conversation, Message
│   │   ├── value_objects/
│   │   │   ├── ids.py                   # Strongly-typed NewType/VO IDs
│   │   │   ├── enums.py                 # FailureCategory, EvalCaseType, ToolName, RunStatus
│   │   │   └── scores.py                # ScoreBreakdown
│   │   ├── protocols/                   # Typing.Protocol interfaces (DIP)
│   │   │   ├── llm_gateway.py           # LLMGatewayProtocol
│   │   │   ├── vector_store.py          # VectorStoreProtocol
│   │   │   ├── document_parser.py       # DocumentParserProtocol
│   │   │   ├── tool.py                  # AgentToolProtocol
│   │   │   ├── cache.py                 # CacheProtocol
│   │   │   └── repositories.py          # ProjectRepo, AgentRepo, EvalRepo, ChatRepo
│   │   └── exceptions.py                # DomainError hierarchy
│   │
│   ├── infrastructure/                  # Concrete adapters & persistence
│   │   ├── supabase/
│   │   │   ├── client.py                # Async Supabase client factory
│   │   │   ├── models.py                # DB row dataclasses / table schemas
│   │   │   ├── storage.py               # Supabase Storage adapter
│   │   │   ├── pgvector_store.py        # VectorStoreProtocol impl
│   │   │   └── repositories/            # Concrete repo implementations
│   │   ├── llm/
│   │   │   ├── litellm_adapter.py       # LLMGatewayProtocol impl + retry/fallback
│   │   │   └── embeddings.py            # CF Workers AI / fallback embedder
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py            # pdfplumber / pypdf extractor
│   │   │   ├── csv_parser.py            # pandas / csv extractor
│   │   │   └── chunker.py               # Configurable overlap chunker
│   │   ├── tools/                       # Registered Agent Tools (3-4 core tools)
│   │   │   ├── registry.py              # ToolRegistry (Factory + @lru_cache)
│   │   │   ├── csv_lookup.py            # Query structured CSV documents
│   │   │   ├── calculator.py            # Safe AST math evaluator
│   │   │   ├── weather_http.py          # Keyless Open-Meteo HTTP API
│   │   │   └── current_date.py          # Deterministic UTC/local date-time
│   │   └── cache/
│   │       └── ttl_cache.py             # Thread-safe in-memory TTLCache
│   │
│   ├── application/                     # Use cases, DTOs, DI, Pipeline
│   │   ├── dtos/                        # Pydantic v2 DTOs with Annotated[...]
│   │   ├── container.py                 # Dependency Injection container
│   │   ├── prompts/                     # Versioned, committed prompt templates
│   │   │   ├── intake_prompts.py
│   │   │   ├── groundability_prompts.py
│   │   │   ├── generator_prompts.py
│   │   │   ├── eval_gen_prompts.py
│   │   │   ├── judge_prompts.py
│   │   │   └── critic_prompts.py
│   │   └── services/
│   │       ├── document_service.py      # Upload, parse, chunk, embed, dedup
│   │       ├── intake_service.py        # Stage 1: <=5 clarifying questions -> RequirementsDoc
│   │       ├── groundability_service.py # Stage 2: Verify brief against docs
│   │       ├── agent_generator.py       # Stage 3: Prompt + retrieval + tools + contract
│   │       ├── eval_generator.py        # Stage 4: >=20 cases (answerable, refusal, edge)
│   │       ├── judge_service.py         # Stage 5: Deterministic + bias-defended LLM judge
│   │       ├── critic_optimizer.py      # Stage 6: Classify failures & targeted fix (<=3 iters)
│   │       ├── reporter_service.py      # Stage 7: Honest report & artifact export
│   │       ├── pipeline_orchestrator.py # End-to-end unattended ForgeAI loop
│   │       └── chat_runner_service.py   # Stage 8: Generic runnable agent execution
│   │
│   └── presentation/                    # FastAPI HTTP/SSE boundary + AOP
│       ├── dependencies.py              # Annotated[Service, Depends(...)]
│       ├── middleware/
│       │   ├── auth.py                  # Supabase JWT verification
│       │   └── telemetry.py             # AOP request timing & correlation IDs
│       ├── aop/
│       │   ├── cached.py                # @cached_llm_call decorator
│       │   └── rate_limit_guard.py      # @with_rate_limit_backoff decorator
│       ├── controllers/                 # Thin orchestration of DTO <-> Service
│       ├── routes/                      # FastAPI APIRouter endpoints
│       └── handlers/                    # Global exception -> ProblemDetails JSON
└── tests/
    ├── unit/                            # Fast, mocked Protocol tests
    └── integration/                     # Pipeline + DB/HTTP tests
```

---

## 3. Frontend Folder Structure (`client/`, Next.js 16 App Router)

Follows [client/AGENTS.md](../client/AGENTS.md) and [client/DESIGN.md](../client/DESIGN.md):

```text
client/
├── app/
│   ├── layout.tsx                       # Root layout, Anthropic Serif/Sans/Mono, theme
│   ├── globals.css                      # Anthropic Design System tokens
│   ├── page.tsx                         # Workspace entry (RSC)
│   ├── login/page.tsx                   # Supabase Auth login
│   ├── (workspace)/
│   │   ├── layout.tsx                   # Collapsible Sidebar + Topbar shell
│   │   ├── page.tsx                     # New ForgeAI Agent Builder session
│   │   └── projects/[id]/page.tsx       # Project chat + Live Eval Observability
│   └── agent/[slug]/page.tsx            # Public/Shareable Runnable Agent UI
├── features/
│   ├── sidebar/                         # Collapsible conversation & project history
│   ├── builder-chat/                    # Intake Q&A, file dropzone, brief submission
│   ├── eval-observability/              # Live iteration timeline, scorecards, failures
│   └── agent-runner/                    # Generic chat UI loading any AgentDefinition
├── components/ui/                       # shadcn/ui primitives
├── lib/
│   ├── server/                          # Server-only Supabase client & fetchers
│   └── client/                          # Browser Supabase client & API client
└── types/                               # Zod schemas & TypeScript contracts
```

---

## 4. Supabase Database Schema (PostgreSQL + pgvector)

All tables enforce Row Level Security (`user_id = auth.uid()`), with a public read policy for published `agent_definitions` accessed via `/agent/[slug]`.

1. **`forge_projects`**: `id (uuid PK)`, `user_id (uuid FK)`, `title`, `brief (text)`, `status (enum)`, `requirements_doc (jsonb)`, `groundability_report (jsonb)`, `created_at`, `updated_at`.
2. **`documents`**: `id (uuid PK)`, `project_id (uuid FK)`, `filename`, `mime_type`, `storage_path`, `content_hash (text)`, `metadata (jsonb)`, `created_at`.
3. **`document_chunks`**: `id (uuid PK)`, `document_id (uuid FK)`, `project_id (uuid FK)`, `chunk_index (int)`, `content (text)`, `token_count (int)`, `embedding vector(768)`, `metadata (jsonb)`.
   - Index: `CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops);`
   - Full-text column `fts tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` + GIN index for hybrid retrieval.
4. **`agent_definitions`**: `id (uuid PK)`, `project_id (uuid FK)`, `slug (text UNIQUE)`, `version (int)`, `system_prompt (text)`, `retrieval_config (jsonb)`, `selected_tools (text[])`, `output_contract (jsonb)`, `honest_report (jsonb)`, `is_published (bool)`, `created_at`.
5. **`eval_cases`**: `id (uuid PK)`, `project_id (uuid FK)`, `case_type (answerable|refusal|edge)`, `question (text)`, `expected_sources (text[])`, `expected_facts (text[])`, `should_refuse (bool)`, `rationale (text)`.
6. **`eval_runs`**: `id (uuid PK)`, `project_id (uuid FK)`, `agent_version (int)`, `iteration (int)`, `overall_score (float)`, `pass_rate (float)`, `metrics (jsonb)`, `status (text)`, `created_at`.
7. **`eval_results`**: `id (uuid PK)`, `eval_run_id (uuid FK)`, `eval_case_id (uuid FK)`, `agent_response (text)`, `retrieved_chunk_ids (uuid[])`, `grounded (bool)`, `correct (bool)`, `refusal_accurate (bool)`, `failure_category (text)`, `judge_reasoning (text)`, `latency_ms (int)`.
8. **`iteration_logs`**: `id (uuid PK)`, `project_id (uuid FK)`, `iteration (int)`, `score_before (float)`, `score_after (float)`, `failure_summary (jsonb)`, `targeted_fix (jsonb)`, `created_at`.
9. **`conversations`** & **`messages`**: Standard chat history for both the ForgeAI builder flow and the runnable `/agent/[slug]` sessions.

---

## 5. Multi-Provider Routing & 3-Layer Caching

### LiteLLM Routing Strategy
- **Tier 1 — Orchestrator & Complex Synthesis** (`orchestrator-primary`): `gemini/gemini-2.5-flash-lite` (15 RPM, ~1000+ RPD, 250K TPM) → fallback `nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1` → fallback `groq/openai/gpt-oss-120b`.
- **Tier 2 — Fast Generation & Judge** (`fast-judge`): `groq/openai/gpt-oss-20b` & `groq/qwen/qwen3-32b` (30 RPM, 1K RPD, 8K TPM — keep prompts < 2,500 tokens!) → fallback `gemini/gemini-2.5-flash-lite`.
- **Tier 3 — Critic & Quality Escalation** (`critic-reasoning`): `nvidia_nim/nemotron` (40 RPM) → fallback `groq/openai/gpt-oss-120b`.
- **Tier 4 — Embeddings & Guardrails**: Cloudflare Workers AI (`@cf/baai/bge-base-en-v1.5`, 768-dim, 300 RPM, low neuron cost) for embeddings; `groq/meta-llama/llama-prompt-guard-2-86m` for prompt-injection checks.

### 3-Layer Caching (Essential for Free-Tier Survival)
1. **L1 In-Memory Prompt Cache (`TTLCache`)**: Key = `sha256(model + normalized_messages + temperature)`. Avoids duplicate LLM calls on retries or unchanged chunks.
2. **L2 Embedding Cache (Postgres `document_chunks`)**: Key = `sha256(chunk_content)`. Never re-embed identical text across runs.
3. **L3 Eval Score Cache**: During Critic-Optimizer iterations, only re-run & re-judge cases affected by the targeted fix OR full regression on final iteration if budget permits (configurable flag, default: full re-eval on modified prompt/retrieval, cached for untouched deterministic checks).

