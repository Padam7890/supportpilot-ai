"""Bounded evidence accepted from server-authorized retrieval and tools."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

EvidenceKind = Literal["knowledge", "catalog", "verified_order"]
EvidenceStatus = Literal["verified", "missing", "denied", "retrieval_failed"]
MAX_EVIDENCE_ITEMS = 6
MAX_EVIDENCE_CHARACTERS = 6000


@dataclass(frozen=True)
class EvidenceItem:
    kind: EvidenceKind
    content: str
    source_id: str
    chunk_index: int | None = None


@dataclass(frozen=True)
class ResponseEvidence:
    items: tuple[EvidenceItem, ...] = ()
    status: EvidenceStatus = "missing"

    def __post_init__(self) -> None:
        if bool(self.items) != (self.status == "verified"):
            raise ValueError("Only verified evidence can contain facts")
        if len(self.items) > MAX_EVIDENCE_ITEMS or (
            sum(len(item.content) for item in self.items) > MAX_EVIDENCE_CHARACTERS
        ):
            raise ValueError("Evidence exceeds the response budget")
        if any(not item.source_id or not item.content.strip() for item in self.items):
            raise ValueError("Evidence must have content and provenance")


def knowledge_evidence(matches: Sequence[Mapping[str, object]]) -> ResponseEvidence:
    items = []
    for match in matches[:MAX_EVIDENCE_ITEMS]:
        excerpt, document_id, chunk_index = (
            match.get("excerpt"), match.get("document_id"), match.get("chunk_index"),
        )
        if (
            isinstance(excerpt, str) and excerpt.strip()
            and isinstance(document_id, str) and document_id
            and type(chunk_index) is int
        ):
            items.append(EvidenceItem("knowledge", excerpt.strip()[:800], document_id, chunk_index))
    return ResponseEvidence(tuple(items), "verified" if items else "missing")
