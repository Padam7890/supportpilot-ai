# RAG operations

## Migrations

1. Run `alembic upgrade head` (or `docker compose run --rm migrate`).
2. Revision `0072_embedding_hnsw_index` promotes `document_embeddings.embedding` to `vector(1536)` and creates `ix_document_embeddings_hnsw_cosine` only when no rows violate the dimension constraint. On mixed-dimension datasets the migration skips the index instead of failing the deploy.
3. Revision `0073_embedding_source_hash` adds `document_embeddings.content_hash`. Rows that cannot be backfilled from `document_chunks` are removed and must be re-embedded.

## Verify indexes

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'document_embeddings'
ORDER BY indexname;
```

## Tenant-scoped semantic query plan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.document_id, c.chunk_index
FROM document_chunks c
JOIN document_embeddings e
  ON e.organization_id = c.organization_id
 AND e.document_id = c.document_id
 AND e.chunk_index = c.chunk_index
 AND e.content_hash = c.content_hash
WHERE c.organization_id = '<org-uuid>'
ORDER BY e.embedding <=> '[...]'::vector
LIMIT 6;
```

## Embedding backfill

After changing `ai_embedding_model`, `ai_embedding_version`, or dimensions, enqueue jobs via the knowledge API backfill endpoint or reprocess documents so chunk hashes and vectors align.

## Evaluation

Deterministic corpus checks (no LLM cost):

```bash
cd backend && python scripts/rag_eval_report.py
```

Integration metrics (Recall@6, MRR) require `TEST_DATABASE_URL` and live in `tests/rag_eval/`.
