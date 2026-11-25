# Eval Generator, Judge & Critic-Optimizer Specification

This document specifies the core quality mechanisms required by [docs/overview.md](overview.md) (Requirements 2, 4, 5, 6, 7).

---

## 1. Groundability Guard (Requirement 2)
Runs immediately after `RequirementsDoc` is finalized and documents are indexed:
1. For every topic in `must_answer_topics`, embed the topic query and run hybrid search (`top_k=5`) against `document_chunks`.
2. Pass the topic + top retrieved chunks to the Groundability prompt (`gemini-2.5-flash-lite`).
3. Output `TopicGroundability(is_grounded, confidence, supporting_documents, gap_reason)`.
4. **Hard Gate:** If any `must_answer_topic` has `is_grounded=False` or `confidence < 0.45`, mark `GroundabilityReport.is_passable = False`, surface the exact gap to the user, and **block** agent generation unless the user narrows the scope.

---

## 2. Eval Generator (Requirement 4)
Generates **at least 20 test cases** strictly from the uploaded documents (generation prompts committed in `application/prompts/eval_gen_prompts.py`):
- **10–12 Answerable Cases (`answerable`):** Grounded in specific chunks; includes `expected_sources` (filenames) and `expected_facts` (2–4 atomic verifiable facts).
- **5–6 Out-of-Scope Refusal Cases (`refusal`):** Plausible-sounding questions related to the domain or covered in `must_refuse_topics` that are **absent** from the documents (`should_refuse=True`).
- **4–5 Edge Cases (`edge`):** Ambiguous phrasing, multi-document synthesis (facts spanning ≥ 2 files), or boundary conditions (dates, numeric calculations, CSV lookups).

---

## 3. Bias-Defended Judge (Requirement 5)
To defend against LLM-as-judge failure modes (**position bias**, **verbosity bias**, **self-preference**) while staying within free-tier RPM:

### Layer A — Deterministic Pre-Checks (0 LLM calls)
1. **Refusal Check:** If `should_refuse=True`, check against refusal patterns + absence of fabricated specifics.
2. **Citation Presence:** If `output_contract.require_citations=True` and `should_refuse=False`, verify a valid document filename from `expected_sources` is cited.
3. **Fact Anchor Check:** Check presence of key numeric/entity tokens from `expected_facts` (case-insensitive / normalized).
4. **Word Limit Check:** Flag violations of `output_contract.max_response_words`.

### Layer B — Bias-Defended LLM Judge (1 structured call per case)
1. **Cross-Model Separation (Self-Preference Defense):** The Judge MUST NOT use the exact same model that generated the agent's response (e.g., if Agent runs on `gpt-oss-20b`, Judge runs on `qwen3` or `gemini-2.5-flash-lite`).
2. **Verbosity Bias Defense:** Strip filler/markdown fluff and truncate/normalize candidate responses to a concise factual summary window before scoring; instruct the judge explicitly: *"Score strictly on factual alignment with `expected_facts` and `retrieved_context`; longer answers do NOT earn higher points."*
3. **Position Bias Defense:** When comparing retrieved chunks or candidate facts, shuffle chunk order deterministically by `hash(eval_case_id)` and use rubric-anchored binary booleans (`grounded`, `correct`, `refusal_accurate`) rather than relative A-vs-B ranking.

---

## 4. Critic–Optimizer Loop (Requirement 6)
Bounded to **maximum 3 iterations**:
1. **Classify Every Failure** into one of 4 categories:
   - `retrieval_miss`: Expected source/fact was in the corpus but not in `retrieved_chunk_ids`.
   - `prompt_defect`: Facts were retrieved, but the agent ignored instructions, tone, format, or tool usage.
   - `hallucination`: Agent stated facts not supported by `retrieved_chunk_ids`.
   - `wrong_refusal`: Agent refused an answerable question OR answered an out-of-scope refusal question.
2. **Apply Targeted Fix (NO full regeneration):**
   - Dominant `retrieval_miss` → adjust `RetrievalConfig` (`top_k`, `similarity_threshold`, `hybrid_search`, or `chunk_size`).
   - Dominant `prompt_defect` / `hallucination` / `wrong_refusal` → surgical patch to `system_prompt` or `output_contract` targeting the specific failure pattern.
3. **Log Every Iteration:** Record `score_before`, `score_after`, `failures_addressed`, `what_changed`, and `why` in `iteration_logs`.
4. **Early Stopping:** Stop if `pass_rate >= 0.90` OR iteration reaches `3` OR improvement `< 0.02` (budget guard).

---

## 5. Honest Reporting (Requirement 7)
`ReporterService` compiles `HonestReport` containing:
- Final `AgentDefinition`
- Per-iteration scorecard table
- Explicit list of **remaining failing cases** with their `failure_category` and root-cause explanation
- Known limitations (e.g., sparse document coverage, ambiguous phrasing edge cases)
Never round up or hide failures—an honest 78% with clear diagnosis is the target standard.

