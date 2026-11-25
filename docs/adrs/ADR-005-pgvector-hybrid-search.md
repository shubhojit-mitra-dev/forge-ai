# ADR-005: `pgvector` + Postgres FTS Hybrid Search (RRF) over S3 Vectors

- **Status:** Accepted
- **Date:** 2026-11-25

## Context
Document retrieval must support both semantic similarity (paraphrased HR/procurement questions) and exact lexical matching (part numbers, SKUs, policy section IDs). Amazon S3 Vectors has no free tier and higher cold-query latency.

## Decision
Store 768-dimensional embeddings in Supabase `document_chunks` with an HNSW cosine index (`vector_cosine_ops`) alongside a generated `tsvector` GIN index, fusing dense and lexical rankings via **Reciprocal Rank Fusion (RRF)** in SQL.

## Consequences
- **Positive:** Zero extra vector-DB cost; sub-50ms hybrid retrieval; strict `project_id` isolation via SQL/RLS.
- **Negative:** Coupled to PostgreSQL `pgvector` (acceptable given ADR-002).

