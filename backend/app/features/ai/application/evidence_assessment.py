"""Conservative, deterministic evidence checks for retrieved support snippets.

A matching document is not itself proof that the requested policy or product
fact is present. This helper is advisory until connected to answer generation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Sequence


@dataclass(frozen=True)
class EvidenceAssessment:
    supported: bool
    reason: str
    matched_terms: tuple[str, ...] = ()


_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "do", "does", "i", "you", "your",
    "what", "when", "where", "how", "can", "could", "please", "tell",
    "me", "about", "for", "and", "or", "to", "in", "of", "it", "my",
})


def assess_knowledge_evidence(
    question: str, excerpts: Sequence[str], *, min_overlap: int = 1
) -> EvidenceAssessment:
    """Cheap lexical guard, not a semantic entailment or hallucination detector."""
    if min_overlap < 1:
        raise ValueError("min_overlap must be positive")
    terms = {
        term for term in re.findall(r"[\w\u0900-\u097f]+", question.casefold())
        if len(term) > 2 and term not in _STOPWORDS
    }
    if not excerpts:
        return EvidenceAssessment(False, "no_sources")
    if not terms:
        return EvidenceAssessment(False, "query_too_ambiguous")
    text = " ".join(excerpts).casefold()
    source_terms = set(re.findall(r"[\w\u0900-\u097f]+", text))
    matched = tuple(sorted(terms & source_terms))
    if len(matched) < min_overlap:
        return EvidenceAssessment(False, "insufficient_lexical_overlap", matched)
    return EvidenceAssessment(True, "lexical_candidate_only", matched)
