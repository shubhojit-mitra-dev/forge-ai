# Phase 6: Two Full Demo Runs & Artifact Commits

- **Worktree:** `git worktree add ../forge-ai-phase-6 -b feat/phase-6-demos`
- **Progress File:** `docs/progress/phase-6-progress.md`

## Tasks
1. **Demo 1 — Shore-Staff HR Policy Assistant (`artifacts/demos/hr-policy/`):**
   - Prepare 3 HR Policy PDFs (`leave_policy.pdf`, `travel_expense_policy.pdf`, `code_of_conduct.pdf`) + commit `synthesis_prompts.md`.
   - Run ForgeAI unattended end-to-end.
   - Verify tool discipline: `weather_http` and `csv_lookup` are NOT attached.
2. **Demo 2 — Ship-Spares Procurement Assistant (`artifacts/demos/ship-spares/`):**
   - Prepare `spares_catalogue.csv`, `supplier_terms.pdf`, `customs_freight_guide.pdf` + commit `synthesis_prompts.md`.
   - Run ForgeAI unattended end-to-end.
   - Verify tool discipline: `csv_lookup` + `calculator` ARE attached; `weather_http` is NOT attached.
3. **Commit All Artifacts Atomically:**
   - `brief.txt`, `documents/`, `requirements_doc.json`, `groundability_report.json`, `agent_definition.json`, `eval_set.json` (≥ 20 cases), `iteration_logs.json`, `scorecard.json`, `honest_report.md`.

## Verification Gate
- Audit every item in [docs/overview.md](../../docs/overview.md) (Requirements 1–9) and [docs/demo-plan.md](../../docs/demo-plan.md).
- Confirm zero demo-specific hardcoding anywhere in `app/`.

