"""Conservative claim-level checks for knowledge-grounded support responses.

This module never treats retrieval overlap as semantic entailment. It is an
additional safety gate for citations and numeric claims, not an LLM judge.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_CITATION = re.compile(r"\[(?:source|doc)\s*:?\s*(\d+)\]", re.IGNORECASE)
_NUMBER = re.compile(
    r"(?<![\w])\d+(?:,\d{3})*(?:\.\d+)?(?:\s*%|\s*(?:days?|hours?|weeks?|months?|years?))?",
    re.IGNORECASE,
)
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")


@dataclass(frozen=True)
class ClaimCheck:
    accepted: bool
    reason: str
    cited_source_indices: tuple[int, ...] = ()
    unsupported_numbers: tuple[str, ...] = ()


def check_grounded_claims(
    response: str,
    sources: Sequence[Mapping[str, object]],
    *,
    require_citations: bool = True,
) -> ClaimCheck:
    """Check cited source indices and exact numeric claims against cited excerpts.

    Indexing is one-based. Missing/invalid citations fail closed. Numeric
    matches are conservative lexical checks, not proof of policy correctness.
    """
    cited = tuple(sorted({int(value) for value in _CITATION.findall(response)}))
    if not sources:
        return ClaimCheck(False, "no_sources", cited)
    if require_citations and not cited:
        return ClaimCheck(False, "missing_citations")
    if any(index < 1 or index > len(sources) for index in cited):
        return ClaimCheck(False, "invalid_citation_index", cited)
    evidence = " ".join(
        str(sources[index - 1].get("excerpt", ""))
        for index in cited
    ) if cited else " ".join(str(source.get("excerpt", "")) for source in sources)
    answer_without_citations = _CITATION.sub("", response)
    # Preserve units: 7 days and 7 weeks are not interchangeable.
    # Normalize 1,000 to 1000 while preserving decimal precision.
    def numeric_claims(value: str) -> set[str]:
        return {
            _THOUSANDS_SEPARATOR.sub("", item.casefold()).strip()
            for item in _NUMBER.findall(value)
        }

    numbers = numeric_claims(answer_without_citations)
    source_numbers = numeric_claims(evidence)
    missing = tuple(sorted(numbers - source_numbers))
    if missing:
        return ClaimCheck(False, "unsupported_numeric_claim", cited, missing)
    return ClaimCheck(True, "lexical_checks_passed", cited)


def check_generated_answer(
    response: str,
    sources: Sequence[Mapping[str, object]],
) -> ClaimCheck:
    """Delivery gate for generated knowledge answers.

    Existing replies do not consistently include inline source markers, so
    validate explicit markers when present and always check numeric claims.
    A separate citation-enforcement rollout is needed before requiring markers.
    """
    if not sources:
        return ClaimCheck(True, "no_knowledge_sources")
    return check_grounded_claims(response, sources, require_citations=False)


def check_stream_segment(
    segment: str,
    sources: Sequence[Mapping[str, object]],
) -> ClaimCheck:
    """Conservative segment-level gate for future verified streaming.

    A passing segment is not sufficient for delivery: source authorization and
    final-answer validation must also complete before any bytes are published.
    """
    if not segment.strip():
        return ClaimCheck(False, "empty_segment")
    if not sources:
        return ClaimCheck(False, "no_sources")
    return check_grounded_claims(segment, sources, require_citations=False)
