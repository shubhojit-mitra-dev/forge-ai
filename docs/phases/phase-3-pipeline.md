# Phase 3: Application Core — ForgeAI Pipeline (Stages 1–7)

- **Worktree:** `git worktree add ../forge-ai-phase-3 -b feat/phase-3-pipeline`
- **Progress File:** `docs/progress/phase-3-progress.md`

## Parallel Subagent Workstreams (Strict TDD)

### Subagent A — DTOs, Prompts, Intake & Groundability Guard
- `app/application/dtos/*.py` (Pydantic v2 with `Annotated[...]` and `ConfigDict(frozen=True)`).
- `app/application/prompts/*.py` (committed, versioned prompt templates for all stages).
- `tests/unit/application/test_intake_service.py` → `app/application/services/intake_service.py`
  - Assert clarifying questions never exceed `5`.
- `tests/unit/application/test_groundability_service.py` → `app/application/services/groundability_service.py`
  - Assert unsupported `must_answer` topic raises/returns `is_passable=False` with exact `gap_reason`.

### Subagent B — Agent Generator & Eval Generator
- `tests/unit/application/test_agent_generator.py` → `app/application/services/agent_generator.py`
  - **Tool Discipline Test:** HR brief MUST NOT select `weather_http` or `csv_lookup`; Ship-spares brief MUST select `csv_lookup` + `calculator` and MUST NOT select `weather_http`.
- `tests/unit/application/test_eval_generator.py` → `app/application/services/eval_generator.py`
  - Assert `len(eval_cases) >= 20` spanning `answerable`, `refusal`, and `edge` types.

### Subagent C — Bias-Defended Judge, Critic–Optimizer & Honest Reporter
- `tests/unit/application/test_judge_service.py` → `app/application/services/judge_service.py`
  - Test deterministic pre-checks (refusal regex, citation check, word limit).
  - Test cross-model enforcement (Judge model ≠ Agent model), chunk shuffling, and length normalization.
- `tests/unit/application/test_critic_optimizer.py` → `app/application/services/critic_optimizer.py`
  - Test all 4 failure categories (`retrieval_miss`, `prompt_defect`, `hallucination`, `wrong_refusal`) map to targeted patches (no full regeneration) and stop at max 3 iterations or `< 2%` delta.
- `tests/unit/application/test_reporter_service.py` → `app/application/services/reporter_service.py`
  - Test `HonestReport` includes remaining failures and never inflates scores.
- `app/application/services/pipeline_orchestrator.py` + `app/application/container.py` (DI).

## Verification Gate
- Full `PipelineOrchestrator` integration test with mocked `LLMGatewayProtocol` + `VectorStoreProtocol` completes 3 iterations in `< 2s`.
- `make lint && make typecheck && make test-cov` (≥ 85% coverage).

