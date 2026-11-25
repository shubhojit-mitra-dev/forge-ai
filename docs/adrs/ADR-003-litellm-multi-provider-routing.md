# ADR-003: Multi-Provider LiteLLM Routing with Gemini Primary & Groq/NIM Workers

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
We rely on free-tier APIs with asymmetric bottlenecks:
- **Groq:** 30 RPM, 1,000 RPD, but **8,000 TPM** on `gpt-oss-120b`/`gpt-oss-20b`/`qwen3`. Large document prompts trigger `429`/`413` immediately.
- **NVIDIA NIM:** ~40 RPM, dynamic undocumented throttling, prototyping-only SLA.
- **Gemini 2.5 Flash-Lite:** ~15 RPM, **250,000 TPM**, generous RPD.
- **Cloudflare Workers AI:** 300 RPM, 10,000 Neurons/day.

## Decision
Use LiteLLM Proxy (`litellm_config.yaml`) with role-based model tiers:
1. `orchestrator-primary`: Gemini 2.5 Flash-Lite (high TPM for Intake, Groundability, Agent Gen, Eval Gen) → fallback NIM → Groq.
2. `fast-judge`: Groq (`gpt-oss-20b`, `qwen3-32b`) with strict prompt cap (`≤ 2,500` tokens) → fallback Gemini.
3. `critic-reasoning`: NVIDIA NIM (`nemotron`) for low-volume failure diagnosis → fallback Groq `gpt-oss-120b`.
4. Embeddings: Cloudflare Workers AI (`@cf/baai/bge-base-en-v1.5`, 768-dim) with `sha256(content)` DB deduplication.

## Consequences
- **Positive:** Eliminates single-provider 429 failures during unattended recruiter demos; maximizes free-tier throughput.
- **Negative:** Requires careful prompt-length budgeting before routing to Groq (`TPMGuard` in `LiteLLMAdapter`).

