from app.features.ai.domain.content_hash import hash_chunk_text, hash_document_text


def test_document_and_chunk_hashes_are_stable():
    text = " Returns are accepted within 14 days. "
    assert hash_document_text(text) == hash_document_text("Returns are accepted within 14 days.")
    assert hash_chunk_text("chunk one") != hash_chunk_text("chunk two")
