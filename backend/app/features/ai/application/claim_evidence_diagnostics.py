"""Evaluate answer-level evidence conservatively without claiming semantic entailment.

This is an offline diagnostic. Never use token overlap alone to authorize an
order mutation or certify a generated response as factually supported.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_TOKEN = re.compile(r"[\w\u0900-\u097f]+")
_STOP = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "i", "we", "you", "your",
    "our", "to", "for", "of", "on", "in", "and", "or", "with", "it",
    "this", "that", "can", "will", "may", "be", "have", "has",
})


@dataclass(frozen=True)
class ClaimEvidenceDiagnostic:
    claim: str
    candidate_source_indices: tuple[int, ...]
    matched_terms: tuple[str, ...]
    status: str  # no_sources | no_lexical_candidate | lexical_candidate_unverified


def _terms(value: str) -> set[str]:
    return {term for term in _TOKEN.findall(value.casefold()) if len(term) > 2 and term not in _STOP}


def inspect_claim_evidence(
    claim: str, source_excerpts: Sequence[str], *, minimum_shared_terms: int = 2
) -> ClaimEvidenceDiagnostic:
    """Find candidate excerpts; a match is never proof of truth."""
    if minimum_shared_terms < 1:
        raise ValueError("minimum_shared_terms must be positive")
    if not source_excerpts:
        return ClaimEvidenceDiagnostic(claim, (), (), "no_sources")
    terms = _terms(claim)
    candidates: list[tuple[int, set[str]]] = []
    for index, source in enumerate(source_excerpts):
        shared = terms & _terms(source)
        if len(shared) >= minimum_shared_terms:
            candidates.append((index, shared))
    if not candidates:
        return ClaimEvidenceDiagnostic(claim, (), (), "no_lexical_candidate")
    return ClaimEvidenceDiagnostic(
        claim,
        tuple(index for index, _ in candidates),
        tuple(sorted(set().union(*(shared for _, shared in candidates)))),
        "lexical_candidate_unverified",
    )
