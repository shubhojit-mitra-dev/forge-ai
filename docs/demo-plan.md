# Demo Runs & Unattended Review Plan

## 1. Two Contrasting End-to-End Demonstrations (Requirement 9)
We will run ForgeAI end-to-end on two deliberately distinct domains and commit **all** generated artifacts under `artifacts/demos/`:

### Demo 1: Shore-Staff HR Policy Assistant (`artifacts/demos/hr-policy/`)
- **Brief:** *"I need an assistant that answers HR policy questions for shore staff — leave entitlements, travel reimbursement, remote work rules, and grievance procedures — citing the exact policy section and refusing salary or legal advice."*
- **Documents:** 3 synthesized/public HR Policy PDFs (`leave_policy.pdf`, `travel_expense_policy.pdf`, `code_of_conduct.pdf`).
- **Expected Tool Selection:** `current_date` (for leave/notice calculations) or `[]` — **MUST NOT attach `weather_http` or `csv_lookup`**.

### Demo 2: Ship-Spares Procurement Assistant (`artifacts/demos/ship-spares/`)
- **Brief:** *"I need a procurement assistant for marine engineers to look up spare parts from our vessel inventory CSV, calculate order quantities and landed costs, and check supplier lead-time terms from our procurement PDFs."*
- **Documents:** `spares_catalogue.csv` + `supplier_terms.pdf` + `customs_freight_guide.pdf`.
- **Expected Tool Selection:** `csv_lookup`, `calculator`, `current_date` — **MUST NOT attach `weather_http`**.

---

## 2. Committed Artifact Structure per Demo
```text
artifacts/demos/<demo-name>/
├── brief.txt
├── documents/                 # Input PDFs/CSVs + synthesis_prompts.md
├── requirements_doc.json      # Stage 1 output
├── groundability_report.json  # Stage 2 output
├── agent_definition.json      # Stage 3 / Final optimized definition
├── eval_set.json              # Stage 4 output (>=20 cases)
├── iteration_logs.json        # Stage 6 per-iteration diffs & scores
├── scorecard.json             # Per-iteration metrics
└── honest_report.md           # Stage 7 final human-readable report
```

---

## 3. Unattended Review Readiness Checklist
At the OceanAI review, an unseen brief + document folder will be provided:
- [ ] CLI runner (`python -m forge_ai.cli forge --brief ... --docs ...`) AND Web UI both execute unattended end-to-end.
- [ ] Zero hardcoded demo prompts, filenames, or eval cases in `src/forge_ai/`.
- [ ] All generation prompts (`intake`, `groundability`, `generator`, `eval_gen`, `judge`, `critic`) committed and documented.
- [ ] Generated agent immediately loadable via `python -m forge_ai.cli chat --agent ...` AND via `/agent/[slug]` web route.

---

## 4. Stretch Goals (Attempt Only After All 9 Core Requirements Pass)
1. **UI & Hosting (In Scope):** Next.js on Vercel + FastAPI/LiteLLM on EC2 `t3.small` (`forge-ai.shubhojitmitra.com`).
2. **Budget Enforcement:** Token/call cap + early stopping on `< 2%` delta.
3. **Human Checkpoint:** UI pause after `RequirementsDoc` so requester can edit before generation.
4. **Prompt Tournament:** Generate 2 candidate system prompts in Iter 0, run fast eval subset, pick winner.
5. **Regression Mode:** Re-run stored `eval_set` when new documents are uploaded and diff regressions.

