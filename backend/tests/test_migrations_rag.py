from pathlib import Path

"""Static checks for RAG-related Alembic revisions."""


def test_embedding_hnsw_migration_does_not_use_silent_success_path_only():
    source = Path(
        "migrations/versions/0072_embedding_hnsw_index.py"
    ).read_text(encoding="utf-8")
    assert "ix_document_embeddings_hnsw_cosine" in source
    assert "dimensions <> 1536" in source


def test_embedding_source_hash_migration_backfills():
    source = Path(
        "migrations/versions/0073_embedding_source_hash.py"
    ).read_text(encoding="utf-8")
    assert "content_hash" in source
    assert "document_chunks" in source
