# Phase 7: Production Deployment (EC2 `t3.small` + Vercel)

- **Worktree:** `git worktree add ../forge-ai-phase-7 -b feat/phase-7-deploy`
- **Progress File:** `docs/progress/phase-7-progress.md`

## Tasks
1. **Backend on AWS EC2 `t3.small` (2 vCPU, 2 GB RAM):**
   - Deploy `docker-compose.yml` (`litellm` + `api` services, total RAM ~400–600 MB).
   - Configure Caddy or Nginx reverse proxy with TLS (`api.forge-ai.shubhojitmitra.com`).
2. **Frontend on Vercel:**
   - Connect `client/` root directory to Vercel project (`forge-ai.shubhojitmitra.com`).
   - Configure `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_API_URL`.
3. **Live Smoke Test:**
   - Run an unseen brief + document folder through `https://forge-ai.shubhojitmitra.com` end-to-end.
   - Verify `/agent/<slug>` shareable link loads and answers grounded questions with citations.

## Verification Gate
- `GET https://api.forge-ai.shubhojitmitra.com/api/v1/health` returns `200 OK`.
- Full UI flow + `/agent/<slug>` live chat verified in browser.

