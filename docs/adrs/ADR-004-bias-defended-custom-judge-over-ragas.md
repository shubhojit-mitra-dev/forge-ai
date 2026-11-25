# ADR-004: Custom Two-Stage Bias-Defended Judge over RAGAS

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
RAGAS executes multiple LLM calls per test case per metric (500+ LLM calls for 20 cases × 5 metrics), which exhausts free-tier RPD/TPM within a single 3-iteration Critic–Optimizer run. Furthermore, `docs/overview.md` explicitly requires defending LLM-as-judge against **position bias**, **verbosity bias**, and **self-preference**.

## Decision
Implement a custom two-stage `JudgeService`:
1. **Stage A (Deterministic Python Checks, 0 LLM calls):** Refusal regex/pattern verification, citation filename verification, expected fact keyword/number anchor checks, word-count contract enforcement, and tool-invocation audit.
2. **Stage B (Bias-Defended LLM Judge, 1 structured JSON call per case):** Cross-model separation (Judge model ≠ Agent model), deterministic chunk-order shuffling (`hash(eval_case_id)`), response length normalization, and rubric-anchored binary booleans (`grounded`, `correct`, `refusal_accurate`).

## Consequences
- **Positive:** Reduces Judge overhead from ~500+ calls/iter to ~20 calls/iter; directly addresses all three LLM-as-judge failure modes cited in the assignment.
- **Negative:** No out-of-the-box RAGAS metric names, though our `grounded`, `correct`, and `refusal_accurate` metrics map 1:1 to `docs/overview.md`.

