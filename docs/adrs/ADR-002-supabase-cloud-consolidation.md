# ADR-002: Supabase Cloud Consolidation over AWS S3 + RDS + Redis

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
Deployment targets a single AWS EC2 `t3.small` (2 vCPU, 2 GB RAM) with rapid delivery as a primary constraint. Standing up separate AWS RDS, S3, S3 Vectors, ElastiCache Redis, and custom JWT Auth introduces significant infrastructure overhead and potential AWS billing surprises.

## Decision
Consolidate Authentication, PostgreSQL, `pgvector` embeddings, Object Storage (`forge-documents` bucket), and Realtime event streaming onto **Supabase Cloud**. Replace Redis with an in-memory `cachetools.TTLCache` inside FastAPI.

## Alternatives Considered
1. **EC2 + Local Postgres + Redis + S3:** Exceeds `t3.small` RAM comfort margin once LiteLLM + FastAPI + Postgres + Redis compete for 2 GB RAM.
2. **AWS Lambda Serverless:** Cold starts and VPC NAT Gateway costs add unnecessary complexity for Phase 0–7 delivery.

## Consequences
- **Positive:** EC2 `t3.small` runs only FastAPI (~100 MB) and LiteLLM (~150 MB). Zero extra DB ops; native RLS security; built-in Realtime WebSockets for live eval observability.
- **Negative:** In-memory `TTLCache` is single-instance scoped (acceptable for single `t3.small` deployment; easily swapped via `CacheProtocol` if horizontally scaled later).

