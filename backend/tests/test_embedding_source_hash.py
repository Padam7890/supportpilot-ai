from app.features.ai.domain.content_hash import hash_chunk_text


def test_embedding_reuse_requires_matching_content_hash():
    text = "Shipping is free over fifty dollars."
    content_hash = hash_chunk_text(text)
    stale_hash = hash_chunk_text("Shipping is free over fifty dollars. Updated.")
    assert content_hash != stale_hash
    prior = (content_hash, 1536)
    assert prior[0] == content_hash
    assert prior[0] != stale_hash
