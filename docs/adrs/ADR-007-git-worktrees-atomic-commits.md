# ADR-007: Git Worktrees & Strict 1–2 File Atomic Commits

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
Parallel subagents implementing multiple subsystems simultaneously risk merge conflicts, polluted `main` history, and unreviewable monolithic commits.

## Decision
1. Each phase runs in an isolated git worktree & feature branch (`feat/phase-<N>-<name>`). `main` is protected and only receives fast-forward/squash-verified merges after the phase gate passes.
2. Every commit is strictly atomic: **1 file per commit** (2 files max only when a module and its unit test are tightly coupled).

## Consequences
- **Positive:** Every commit is cleanly bisectable (`git bisect`), reversible, and auditable by the orchestrator.
- **Negative:** Higher commit count per phase (mitigated by disciplined Conventional Commit messages).

