"""Static checks for RAG-related Alembic revisions."""


def test_embedding_hnsw_migration_does_not_use_silent_success_path_only():
    source = open(
        "migrations/versions/0072_embedding_hnsw_index.py", encoding="utf-8"
    ).read()
    assert "ix_document_embeddings_hnsw_cosine" in source
    assert "dimensions <> 1536" in source


def test_embedding_source_hash_migration_backfills():
    source = open(
        "migrations/versions/0073_embedding_source_hash.py", encoding="utf-8"
    ).read()
    assert "content_hash" in source
    assert "document_chunks" in source
