# Rate-Limit Budgets & Token Math

## 1. Provider Quotas (Verified Free Tier)

| Provider | Model | RPM | RPD | TPM | TPD / Daily Cap | Role |
|---|---|---|---|---|---|---|
| **Google Gemini** | `gemini-2.5-flash-lite` | 15 | ~1,000+ | 250,000 | Project-scoped | Primary Orchestrator, Eval Gen |
| **Groq** | `openai/gpt-oss-120b` | 30 | 1,000 | **8,000** | 200,000 | Critic Escalation |
| **Groq** | `openai/gpt-oss-20b` | 30 | 1,000 | **8,000** | 200,000 | Agent Runner & Fast Judge |
| **Groq** | `qwen/qwen3-32b` | 30 | 1,000 | **8,000** | 200,000 | Cross-Model Judge |
| **Groq** | `meta-llama/llama-prompt-guard-2-86m` | 30 | 14,400 | 15,000 | 500,000 | Input Injection Guard |
| **NVIDIA NIM** | `llama-3.3-nemotron-super-49b-v1` | ~40 | Dynamic | Dynamic | Prototyping SLA | Critic Diagnosis |
| **Cloudflare AI** | `@cf/baai/bge-base-en-v1.5` | 300 | — | — | 10,000 Neurons/day | 768-dim Embeddings |

## 2. Per-Run ForgeAI Budget (Hard Ceiling: 120 Calls / 150K Tokens)

| Pipeline Stage | Target Tier | Calls / Run | Max Prompt Tokens |
|---|---|---|---|
| Stage 1: Intake Interviewer | `orchestrator-primary` | 2 | ≤ 4,000 |
| Stage 2: Groundability Guard | `orchestrator-primary` | 1–3 (batched) | ≤ 8,000 |
| Stage 3: Agent Generator | `orchestrator-primary` | 1–2 | ≤ 6,000 |
| Stage 4: Eval Generator (20+ cases) | `orchestrator-primary` | 3–4 (batched) | ≤ 8,000 |
| Stage 5: Agent Execution (per iter × 3) | `fast-judge` | 20 × 3 = 60 | ≤ 2,000 (Groq-safe) |
| Stage 6: Bias-Defended Judge (per iter × 3) | `fast-judge` (cross-model) | 20 × 3 = 60* | ≤ 2,200 (Groq-safe) |
| Stage 7: Critic Diagnosis (per iter × 3) | `critic-reasoning` | 1 × 3 = 3 | ≤ 4,000 |

*\*With L1/L3 Eval Cache enabled, unchanged passing cases on deterministic checks or unedited retrieval paths skip redundant LLM judge calls, keeping typical 3-iteration runs around **80–100 calls**.*

