# Phase 2: Infrastructure Layer

- **Worktree:** `git worktree add ../forge-ai-phase-2 -b feat/phase-2-infrastructure`
- **Progress File:** `docs/progress/phase-2-progress.md`

## Parallel Subagent Workstreams (Strict TDD)

### Subagent A — LiteLLM Gateway, CF Embeddings & In-Memory Cache
- `tests/unit/infrastructure/test_litellm_adapter.py` → `app/infrastructure/llm/litellm_adapter.py`
  - Test TPM pre-flight guard: payloads `> 2,800` tokens auto-promote from `fast-judge` (Groq) to `orchestrator-primary` (Gemini).
  - Test 429 retry + fallback routing.
- `tests/unit/infrastructure/test_embeddings.py` → `app/infrastructure/llm/embeddings.py`
  - Test Cloudflare Workers AI `@cf/baai/bge-base-en-v1.5` batching + 768-dim output.
- `tests/unit/infrastructure/test_ttl_cache.py` → `app/infrastructure/cache/ttl_cache.py`
  - Test `CacheProtocol` implementation with deterministic SHA-256 keys and TTL expiry.

### Subagent B — Document Parsers & Chunker
- `tests/unit/infrastructure/test_parsers.py` → `app/infrastructure/parsers/pdf_parser.py`, `csv_parser.py`, `chunker.py`
  - Test `pdfplumber` multi-page extraction (including tables).
  - Test CSV row/header extraction.
  - Test overlap chunker (`chunk_size`, `chunk_overlap`, metadata preservation).

### Subagent C — Tool Registry & 4 Core Tools
- `tests/unit/infrastructure/test_tools.py` → `app/infrastructure/tools/registry.py`, `csv_lookup.py`, `calculator.py`, `weather_http.py`, `current_date.py`
  - Test `@lru_cache` `ToolRegistry` factory.
  - Test `calculator` safe AST evaluation (rejects `eval`/`__import__`).
  - Test `csv_lookup` filtering against sample ship-spares CSV.
  - Test `weather_http` with `respx` mocking Open-Meteo API.
  - Test `current_date` deterministic ISO-8601 formatting.

### Subagent D — Supabase Repositories, Storage & `pgvector` Store
- `tests/unit/infrastructure/test_supabase_repos.py` → `app/infrastructure/supabase/client.py`, `storage.py`, `pgvector_store.py`, `repositories/*.py`
  - Test `pgvector` hybrid search RPC call & `sha256(content)` embedding deduplication.
  - Test CRUD mapping between Supabase JSON rows and Domain Entities.

## Verification Gate
- `make lint && make typecheck && make test-cov` passes with all network/DB calls mocked in unit tests.

