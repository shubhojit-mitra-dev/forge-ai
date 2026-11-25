# ADR-006: Path-Based Runnable Agent URLs (`/agent/[slug]`) over Wildcard Subdomains

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
Generated agents must be immediately runnable and shareable (Requirement 8). Wildcard subdomains (`<slug>.forge-ai.shubhojitmitra.com`) require Vercel Pro or automated wildcard TLS certificate provisioning on EC2.

## Decision
Serve runnable agents on path-based URLs: `https://forge-ai.shubhojitmitra.com/agent/<slug>` (e.g., `/agent/hr-policy-14782`).

## Consequences
- **Positive:** Zero-cost Vercel deployment, instant SSL, and identical shareable product UX for recruiters.
- **Negative:** Path-based rather than subdomain-based isolation (cookies scoped to domain, handled cleanly via public `/api/v1/agents/public/{slug}` endpoints).

