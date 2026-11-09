from app.features.ai.application.document_chunking import make_chunks


def test_short_refund_policy_section_is_preserved():
    text = "Returns Policy:\n\n14-day returns on unused items.\n\nExchanges require receipt."
    chunks = make_chunks(text, max_tokens=200, overlap_tokens=16)
    bodies = " ".join(item[0] for item in chunks).casefold()
    assert "14-day" in bodies or "14" in bodies
    assert len(chunks) >= 1
