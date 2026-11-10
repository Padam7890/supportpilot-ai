import pytest

from app.features.ai.application.document_chunking import estimate_tokens, make_chunks
from app.worker import extract_text


def test_chunking_respects_token_budget_and_preserves_overlap():
    text = " ".join(f"word{i}" for i in range(600))
    chunks = make_chunks(text, max_tokens=80, overlap_tokens=16)
    bodies = [content for content, _, _ in chunks]
    assert len(bodies) > 1
    assert all(estimate_tokens(content) <= 80 for content in bodies)
    assert any(
        set(bodies[index].split()) & set(bodies[index + 1].split())
        for index in range(len(bodies) - 1)
    )


def test_text_documents_decode_utf8_bom_and_trim_whitespace():
    assert extract_text("policy.txt", b"\xef\xbb\xbf  return policy  \n") == "return policy"


def test_unsupported_binary_text_fails_cleanly():
    with pytest.raises(UnicodeDecodeError):
        extract_text("policy.md", b"\xff\xfe")
