# Phase 5: Frontend — Next.js 16 Workspace, Live Evals & `/agent/[slug]`

- **Worktree:** `git worktree add ../forge-ai-phase-5 -b feat/phase-5-frontend`
- **Mandatory Reading:** `client/AGENTS.md` (Next.js 16 breaking changes) and `client/DESIGN.md` (Anthropic Design System tokens & surface rhythm).
- **Progress File:** `docs/progress/phase-5-progress.md`

## Parallel Subagent Workstreams

### Subagent A — Auth, Server Layer & Collapsible Sidebar
- `client/lib/server/supabase.ts` + `client/lib/client/supabase.ts`
- `client/app/login/page.tsx` (Supabase Auth)
- `client/app/(workspace)/layout.tsx` (RSC shell with collapsible sidebar `260px` → `56px`)
- `client/features/sidebar/` (grouped project history, status badges, Anthropic cream/slate styling)

### Subagent B — Builder Chat, Document Upload & Intake UI
- `client/features/builder-chat/`
  - Brief composer + drag-and-drop uploader (`PDF`, `CSV`, `MD`, `TXT`)
  - Clarifying questions interactive flow (≤ 5 questions)
  - Groundability Guard banner (pass vs. blocked gap warning)
  - Final Deliverable card: `/agent/[slug]` link + Copy URL + Export Artifacts

### Subagent C — Live Eval Observability & Standalone `/agent/[slug]`
- `client/features/eval-observability/`
  - Toggleable right drawer (`EventSource` SSE + Supabase Realtime)
  - Stage stepper (`Generator → Eval Gen → Iter 1..3 → Report`)
  - Live scorecard, per-iteration diff log, filterable eval case list (`All | Failed | Refusal | Edge`)
- `client/app/agent/[slug]/page.tsx` + `client/features/agent-runner/`
  - Shareable runnable agent chat UI with inline citations, attached tool badges, and Contract/HonestReport inspector drawer.

## Verification Gate
- `cd client && pnpm lint && pnpm exec tsc --noEmit && pnpm build` passes with 0 errors.
- Browser/Playwright verification of login, upload, live eval stream, and `/agent/[slug]` chat.

