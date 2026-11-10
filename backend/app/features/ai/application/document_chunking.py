"""Structure-aware, token-bounded knowledge document chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings

_HEADING = re.compile(
    r"^(?:#{1,6}\s+.+|.+[:：]\s*$|[A-Z][A-Za-z0-9 \-/]{2,60}:$)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class TextSegment:
    text: str
    section_label: str | None = None
    page_number: int | None = None


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def split_blocks(raw_text: str) -> list[TextSegment]:
    """Split on blank lines while preserving headings as block starts."""
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    blocks: list[TextSegment] = []
    current_section: str | None = None
    page: int | None = None
    for part in re.split(r"\n\s*\n+", normalized):
        block = " ".join(part.split())
        if not block:
            continue
        page_match = re.match(r"^---\s*Page\s+(\d+)\s*---\s*(.*)$", block, re.IGNORECASE)
        if page_match:
            page = int(page_match.group(1))
            block = page_match.group(2).strip()
            if not block:
                continue
        if _HEADING.match(block) and len(block) < 120:
            current_section = block.rstrip(":：")
            continue
        blocks.append(TextSegment(block, current_section, page))
    return blocks


def _merge_to_token_budget(
    segments: list[TextSegment],
    *,
    max_tokens: int,
    overlap_tokens: int,
) -> list[TextSegment]:
    chunks: list[TextSegment] = []
    buffer: list[str] = []
    buffer_tokens = 0
    buffer_meta = segments[0] if segments else TextSegment("")

    def flush(*, carry_overlap: bool = True) -> None:
        nonlocal buffer, buffer_tokens, buffer_meta
        if not buffer:
            return
        body = "\n\n".join(buffer).strip()
        if body:
            chunks.append(
                TextSegment(body, buffer_meta.section_label, buffer_meta.page_number)
            )
        if carry_overlap and overlap_tokens > 0 and body:
            overlap_text = body
            while overlap_text and estimate_tokens(overlap_text) > overlap_tokens:
                boundary = overlap_text.find(" ")
                if boundary < 0:
                    overlap_text = ""
                    break
                overlap_text = overlap_text[boundary + 1 :]
            buffer = [overlap_text] if overlap_text else []
            buffer_tokens = estimate_tokens(overlap_text) if overlap_text else 0
        else:
            buffer = []
            buffer_tokens = 0

    for segment in segments:
        segment_tokens = estimate_tokens(segment.text)
        if segment_tokens > max_tokens:
            flush()
            start = 0
            words = segment.text.split()
            while start < len(words):
                window: list[str] = []
                token_count = 0
                index = start
                while index < len(words):
                    candidate = " ".join([*window, words[index]])
                    next_tokens = estimate_tokens(candidate)
                    if window and next_tokens > max_tokens:
                        break
                    window.append(words[index])
                    token_count = next_tokens
                    index += 1
                if window:
                    chunks.append(
                        TextSegment(
                            " ".join(window),
                            segment.section_label,
                            segment.page_number,
                        )
                    )
                if index >= len(words):
                    break
                overlap_words = max(1, overlap_tokens // 4)
                start = max(index - overlap_words, start + 1)
            continue

        if buffer and (
            buffer_meta.section_label != segment.section_label
            or buffer_meta.page_number != segment.page_number
        ):
            flush(carry_overlap=False)
            buffer_meta = segment

        if buffer_tokens + segment_tokens > max_tokens and buffer:
            flush()
            buffer_meta = segment

        if not buffer:
            buffer_meta = segment
        buffer.append(segment.text)
        buffer_tokens += segment_tokens
        if buffer_tokens >= max_tokens:
            flush()

    flush()
    return chunks


def make_chunks(
    text: str,
    *,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[tuple[str, str | None, int | None]]:
    """Return chunk text plus optional section and page metadata."""
    max_tokens = settings.ai_ingestion_chunk_tokens if max_tokens is None else max_tokens
    overlap_tokens = (
        settings.ai_ingestion_chunk_overlap_tokens
        if overlap_tokens is None
        else overlap_tokens
    )
    overlap_tokens = min(overlap_tokens, max(0, max_tokens // 4))
    segments = split_blocks(text)
    if not segments:
        return []
    merged = _merge_to_token_budget(
        segments, max_tokens=max_tokens, overlap_tokens=overlap_tokens
    )
    seen: set[str] = set()
    output: list[tuple[str, str | None, int | None]] = []
    for segment in merged:
        body = segment.text.strip()
        if not body:
            continue
        fingerprint = body.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        output.append((body, segment.section_label, segment.page_number))
    return output

