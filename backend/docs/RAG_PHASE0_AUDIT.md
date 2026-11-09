# Phase 0 — RAG pipeline audit

## Pipeline trace

Upload → `knowledge` API storage → `DocumentIngestionJob` → worker `ingestion.py` (extract, chunk, hash) → `enqueue_document_embeddings` → `embeddings.py` claim/process → `document_embeddings` + `content_hash` → `search_agent_knowledge` (keyword + optional semantic RRF) → `load_execution_context` → `ai_worker` / widget → citations via `citations_remain_authorized`.

## Confirmed issues (status)

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| E1 | **P0** | Stale embedding worker could **cancel** a job when token no longer matched | **Fixed** — ownership via `worker_owns_job`; no cancel on lost fence |
| E2 | **P0** | `succeeded` embedding job while chunks partially embedded | **Fixed** — completeness check before succeed + enqueue coverage gate |
| E3 | **P1** | Vectors searchable when `content_hash` stale | **Fixed** (0073 + join filter) |
| E4 | **P1** | Short policy sections dropped by min-token filter | **Fixed** — dedupe only |
| E5 | **P2** | 0072 skips HNSW silently on dimension mismatch | **Mitigated** — documented in `RAG_OPERATIONS.md` |
| E6 | **P2** | No measured Recall@6 on fixture DB in CI | **Open** — corpus at 100; E2E retrieval eval NOT VERIFIED in default CI |
| E7 | **P1** | Launch gate 95% Recall@6 | **NOT VERIFIED** — no production score |

## Potential risks (not reproduced)

- **Race:** ingest deletes chunks while embed worker in flight — mitigated by document `FOR UPDATE` and revision checks.
- **Race:** lease reclaim + old worker publish — mitigated by worker tokens (E1 fix).
- **Security:** cross-tenant retrieval — covered by `organization_id` + assigned bases; integration tests exist.
- **Ops:** 0073 deletes orphan embeddings — requires re-embed per `RAG_OPERATIONS.md`.

## Test coverage gaps

- Concurrent dual-worker embedding simulation (NOT VERIFIED).
- Live-model answer groundedness (NOT VERIFIED; budget mode not run).
- pgvector EXPLAIN on staging-sized data (NOT VERIFIED).
