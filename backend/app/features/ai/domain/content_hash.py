"""Deterministic hashes for knowledge document revisions and chunk identity."""

import hashlib

PENDING_CONTENT_REVISION = "0" * 64


def hash_text(value: str) -> str:
    """Return a stable SHA-256 hex digest for normalized UTF-8 text."""
    normalized = " ".join(value.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_document_text(full_text: str) -> str:
    """Revision hash for an entire extracted document body."""
    return hash_text(full_text)


def hash_chunk_text(chunk: str) -> str:
    """Per-chunk content hash used to skip unchanged embeddings."""
    return hash_text(chunk)
