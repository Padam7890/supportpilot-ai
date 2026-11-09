from app.features.ai.application.document_chunking import make_chunks, split_blocks


def test_split_blocks_preserves_section_context():
    text = "Returns Policy:\n\nItems may be returned within 14 days.\n\nExchanges are allowed for defects."
    segments = split_blocks(text)
    assert segments
    assert any(segment.section_label == "Returns Policy" for segment in segments)


def test_make_chunks_respects_token_budget():
    body = " ".join(f"word{index}" for index in range(500))
    chunks = make_chunks(f"# Policy\n\n{body}", max_tokens=80, overlap_tokens=10)
    assert len(chunks) > 1
    assert all(len(content) > 0 for content, _, _ in chunks)
