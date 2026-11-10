from app.features.ai.application.document_chunking import make_chunks, split_blocks


def test_split_blocks_preserves_section_context():
    text = "Returns Policy:\n\nItems may be returned within 14 days.\n\nExchanges are allowed for defects."
    segments = split_blocks(text)
    assert segments
    assert any(segment.section_label == "Returns Policy" for segment in segments)


def test_chunks_do_not_duplicate_identical_segments():
    text = "Returns Policy:\n\nSame paragraph.\n\nSame paragraph.\n\nDifferent text about shipping."
    chunks = make_chunks(text, max_tokens=120, overlap_tokens=8)
    bodies = [item[0] for item in chunks]
    assert len(bodies) == len(set(body.casefold() for body in bodies))


def test_make_chunks_respects_token_budget():
    body = " ".join(f"word{index}" for index in range(500))
    chunks = make_chunks(f"# Policy\n\n{body}", max_tokens=80, overlap_tokens=10)
    assert len(chunks) > 1
    assert all(len(content) > 0 for content, _, _ in chunks)


def test_unstructured_text_uses_canonical_chunking():
    text = "Simple product information without headings or paragraph breaks."
    chunks = make_chunks(text, max_tokens=100, overlap_tokens=8)
    assert chunks == [(text, None, None)]


def test_blank_document_produces_no_chunks():
    assert make_chunks(" \n \t ") == []


def test_single_long_word_does_not_hang_overlap_processing():
    # A segment without spaces must not leave the overlap trimming loop stuck.
    from app.features.ai.application.document_chunking import TextSegment, _merge_to_token_budget

    chunks = _merge_to_token_budget(
        [TextSegment("x" * 20), TextSegment("y" * 20)],
        max_tokens=5,
        overlap_tokens=1,
    )
    assert [chunk.text for chunk in chunks] == ["x" * 20, "y" * 20]
