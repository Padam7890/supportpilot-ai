import pytest

from app.worker import extract_text, make_chunks


def test_chunking_bounds_chunk_size_and_overlaps_adjacent_chunks():
    text = " ".join(f"word{i}" for i in range(600))
    chunks = make_chunks(text, size=240, overlap=40)
    assert len(chunks) > 1
    assert all(len(chunk) <= 240 for chunk in chunks)
    assert any(set(chunks[index].split()) & set(chunks[index + 1].split()) for index in range(len(chunks) - 1))


def test_text_documents_decode_utf8_bom_and_trim_whitespace():
    assert extract_text("policy.txt", b"\xef\xbb\xbf  return policy  \n") == "return policy"


def test_unsupported_binary_text_fails_cleanly():
    with pytest.raises(UnicodeDecodeError):
        extract_text("policy.md", b"\xff\xfe")
