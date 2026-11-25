# Phase 1: Pure Domain Layer

- **Worktree:** `git worktree add ../forge-ai-phase-1 -b feat/phase-1-domain`
- **Rule:** **ZERO** imports from `fastapi`, `pydantic`, `supabase`, `litellm`, `httpx`, or any I/O library inside `app/domain/`.
- **Progress File:** `docs/progress/phase-1-progress.md`

## Parallel Subagent Workstreams (Strict TDD: Write Test First → Implement)

### Subagent A — Value Objects, Enums & Exceptions
- `tests/unit/domain/test_value_objects.py` → `app/domain/value_objects/ids.py`, `enums.py`, `scores.py`
  - Test `EvalCaseType`, `FailureCategory`, `ToolName`, `RunStatus` enum values.
  - Test `ScoreBreakdown` immutability (`frozen=True`, `slots=True`) and pass-rate calculation.
- `tests/unit/domain/test_exceptions.py` → `app/domain/exceptions.py`
  - Hierarchy: `ForgeDomainError` → `GroundabilityBlockedError`, `BudgetExceededError`, `InvalidToolSelectionError`, `EntityNotFoundError`.

### Subagent B — Domain Entities (`@dataclass(slots=True)`)
- `tests/unit/domain/test_project_and_docs.py` → `app/domain/entities/project.py`, `document.py`, `requirements.py`
  - Test `ClarifyingQA` max-5 invariant on `RequirementsDoc`.
  - Test `GroundabilityReport.is_passable` fails when any `must_answer` topic has `is_grounded=False`.
- `tests/unit/domain/test_agent_and_evals.py` → `app/domain/entities/agent_definition.py`, `evaluation.py`, `conversation.py`
  - Test `AgentDefinition` version bumping & immutable `RetrievalConfig` / `OutputContract`.
  - Test `IterationLog` bounded `1 <= iteration <= 3`.

### Subagent C — Domain Protocols (`typing.Protocol`)
- `app/domain/protocols/llm_gateway.py` (`LLMGatewayProtocol`, `EmbeddingGatewayProtocol`)
- `app/domain/protocols/vector_store.py` (`VectorStoreProtocol`)
- `app/domain/protocols/document_parser.py` (`DocumentParserProtocol`)
- `app/domain/protocols/tool.py` (`AgentToolProtocol`)
- `app/domain/protocols/cache.py` (`CacheProtocol`)
- `app/domain/protocols/repositories.py` (`ProjectRepositoryProtocol`, `AgentRepositoryProtocol`, `EvalRepositoryProtocol`, `ChatRepositoryProtocol`)

## Atomic Commit & Gate
- Commit each entity/test pair atomically (1–2 files max).
- Gate: `make lint && make typecheck && make test-cov` (≥ 90% on `app/domain/`).

