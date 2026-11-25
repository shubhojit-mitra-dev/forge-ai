# ADR-001: Plain Async Python + Pydantic + LiteLLM over LangChain / LangGraph

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
ForgeAI's factory pipeline is a deterministic, linear workflow with one bounded optimization loop:
`Intake → Groundability → AgentGenerator → EvalGenerator → [Judge → Critic → Optimizer]×(≤3) → Reporter`.
Every stage runs on small, imperfect open models with strict free-tier rate limits. During unattended evaluation, any failure must be immediately diagnosable with clean stack traces and deterministic unit tests.

## Decision
Implement the entire pipeline in plain async Python 3.12+ using `typing.Protocol` interfaces, `@dataclass(slots=True)` domain entities, Pydantic v2 DTOs, and LiteLLM as the unified LLM gateway.

## Alternatives Considered
1. **LangGraph:** Designed for cyclic, multi-actor stateful graphs. Adds unnecessary state-machine boilerplate for a 1-loop linear pipeline.
2. **LangChain (LCEL):** Introduces ~50 transitive dependencies, opaque runnable chains, and breaking version churn that obscures debugging and complicates `mypy --strict`.

## Consequences
- **Positive:** 100% `mypy --strict` compliance; sub-second unit tests via `Protocol` mocks; full control over token budgets, caching, and prompt formatting.
- **Negative:** We own ~100 lines of PDF/CSV chunking and pipeline orchestration code directly (trivial maintenance cost).

