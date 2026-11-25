# Circuit Breakers, Error Budgets & SLOs

## 1. Service Level Objectives (SLOs)

| SLI | Target (SLO) | Measurement Window |
|---|---|---|
| **Unattended Factory Completion Rate** | ≥ 99.0% | Per 100 valid runs |
| **End-to-End Factory Latency (3 iters, 20 evals)** | ≤ 180s (P95) | `forge_run` span |
| **Runnable Agent Chat P95 Latency** | ≤ 3.5s | FastAPI AOP `@timed_operation` |
| **Groundability False-Pass Rate** | 0.0% on unsupported `must_answer` | Automated test gate |
| **Tool Discipline Precision** | 100.0% (zero irrelevant tools) | Automated test gate |
| **Unit/App Test Coverage** | ≥ 85.0% | `pytest --cov=app` |
| **Static Type Safety (`mypy --strict`)** | 0 errors | CI + phase gate |

## 2. Circuit Breakers & Early Stopping

1. **TPM Pre-Flight Guard:** Before sending any prompt to a Groq deployment (`8K TPM` cap), `LiteLLMAdapter` estimates tokens (`len(text) // 4`). Any payload `> 2,800` tokens is automatically promoted to `orchestrator-primary` (Gemini `250K TPM`).
2. **429 Jittered Backoff + Cooldown:** On HTTP `429`, LiteLLM retries up to `3` times with exponential jitter (`1s → 2s → 4s`), then marks the deployment in `60s` cooldown and routes to the next fallback.
3. **Iteration Diminishing-Returns Breaker:** In the Critic–Optimizer loop, if `score_after - score_before < 0.02` (2% improvement) or `remaining_call_budget < 25`, stop iterating early and emit `HonestReport` documenting the early stop.

