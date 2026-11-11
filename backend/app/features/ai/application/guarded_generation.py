"""Compose and verify one complete reply before persistence or delivery."""

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from app.features.ai.application.claim_grounding import CITATION_PATTERN
from app.features.ai.application.conversation_context_builder import build_agent_input
from app.features.ai.application.conversation_response_composer import compose_natural_answer
from app.features.ai.application.conversation_response_evidence import knowledge_evidence
from app.features.ai.application.conversation_verified_order_evidence import AuthorizedOrderSnapshot
from app.features.ai.application.generation_metrics import log_generation_metrics
from app.features.ai.application.semantic_claim_verifier import (
    normalize_candidate,
    verify_candidate,
)
from app.features.ai.infrastructure.llm_gateway import AIProviderError

logger = logging.getLogger(__name__)

_SAFE_FALLBACK = (
    "I couldn't verify the details in the available sources. "
    "Please contact our support team to confirm."
)


@dataclass(frozen=True)
class GuardedDraft:
    text: str
    accepted: bool
    grounding_reason: str | None
    citations: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    usage: dict[str, int]
    model_name: str | None
    expected_answer: Literal["delivery_date", "contextual"] | None = None
    answer_resolution: Literal["answered", "insufficient_evidence", "no_relevant_evidence", "needs_clarification"] | None = None


async def generate_guarded_draft(
    *,
    execution_id: str,
    execution_kind: str,
    question: str,
    instructions: str | None,
    transcript: list[dict[str, str]],
    context: list[dict[str, Any]],
    integration_context: dict[str, Any],
    citations: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    requires_evidence: bool,
    correlation_id: str | None,
) -> GuardedDraft:
    started = time.monotonic()
    # The encrypted snapshot is populated only by the authorized teammate
    # lookup. Never pass it to the composer or its semantic reviewer.
    order_text = None
    if integration_context:
        if execution_kind != "reply_draft":
            raise PermissionError("Only a teammate draft can consume a verified order snapshot")
        order = AuthorizedOrderSnapshot.model_validate(integration_context).as_evidence()
        order_text = order.items[0].content

    evidence = knowledge_evidence(context)
    if order_text and not evidence.items:
        return GuardedDraft(order_text, True, None, [], outcomes, {}, None)
    if requires_evidence and evidence.status != "verified":
        logger.info("rag_grounding_debug execution_id=%s stage=no_evidence evidence_status=%s evidence_count=%d retrieval=%s", execution_id, evidence.status, len(evidence.items), [{k: outcome.get(k) for k in ("tool", "status", "result_count", "retrieval_outcome", "embedding_status")} for outcome in outcomes if outcome.get("tool") == "tenant_knowledge_search"])
        return GuardedDraft(
            _SAFE_FALLBACK, False, "no_verified_evidence", [],
            [*outcomes, {"tool": "claim_grounding", "status": "blocked", "reason": "no_verified_evidence"}],
            {}, None, answer_resolution="no_relevant_evidence",
        )
    agent_input = build_agent_input(question, transcript, channel=execution_kind)
    composed = await compose_natural_answer(agent_input, evidence, instructions=instructions)
    # A safe non-answer can miss an entailed policy scope. Reconsider once,
    # then subject the replacement to the same independent grounding verifier.
    # Never force a positive answer or override exceptions in the evidence.
    generation_attempts = 1
    if (
        requires_evidence
        and evidence.items
        and composed.answer_resolution == "insufficient_evidence"
    ):
        reconsidered = await compose_natural_answer(
            agent_input, evidence, instructions=instructions, reconsideration=True,
        )
        generation_attempts = 2
        if reconsidered.answer_resolution == "answered":
            composed = reconsidered
    model_name = composed.model_name[:120] if composed.model_name else None
    usage = dict(composed.usage)
    try:
        verification = await verify_candidate(composed.text, evidence)
    except AIProviderError as exc:
        if exc.code != "execution_token_budget_exceeded":
            raise
        return GuardedDraft(
            _SAFE_FALLBACK, False, exc.code, [],
            [*outcomes, {"tool": "claim_grounding", "status": "blocked", "reason": exc.code}],
            usage, model_name, answer_resolution="insufficient_evidence",
        )
    for key, value in verification.usage.items():
        usage[key] = usage.get(key, 0) + value
    logger.info(
        "rag_grounding execution_id=%s generation_attempts=%d accepted=%s reason=%s "
        "evidence_count=%d citations_recovered=%d",
        execution_id, generation_attempts, verification.accepted, verification.reason, len(evidence.items),
        verification.citations_recovered,
    )
    log_generation_metrics(
        execution_id=execution_id, execution_kind=execution_kind, model_name=model_name,
        started_monotonic=started, usage=usage, streamed=False, correlation_id=correlation_id,
    )
    outcomes = [
        *outcomes,
        {
            "tool": "claim_grounding",
            "status": "completed" if verification.accepted else "blocked",
            "reason": verification.reason,
            "citations_recovered": verification.citations_recovered,
        },
    ]
    if not verification.accepted:
        text = f"{order_text}\\n\\n{_SAFE_FALLBACK}" if order_text else _SAFE_FALLBACK
        return GuardedDraft(text, False, verification.reason, [], outcomes, usage, model_name, answer_resolution="insufficient_evidence")

    available = {(str(c["document_id"]), c["chunk_index"]): c for c in citations}
    selected = []
    for index in verification.source_indices:
        item = evidence.items[index - 1]
        citation = available.get((item.source_id, item.chunk_index))
        if citation is None:
            return GuardedDraft(
                _SAFE_FALLBACK, False, "missing_source_provenance", [], outcomes, usage, model_name, answer_resolution="insufficient_evidence",
            )
        selected.append(citation)
    # Keep verified provenance in structured citations, not customer-visible text.
    # Strip only after verification and provenance checks have succeeded.
    text = CITATION_PATTERN.sub("", normalize_candidate(composed.text))
    text = text.replace(" .", ".").replace(" ,", ",")
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if order_text:
        text = f"{order_text}\n\n{text}"
    # Safety acceptance is not question resolution. Even a verified, polite
    # non-answer may have no citations, as in the Pokhara delivery example.
    # A model cannot mark a knowledge answer resolved without verified provenance.
    resolution = composed.answer_resolution
    if requires_evidence and not selected and resolution != "needs_clarification":
        resolution = "insufficient_evidence"
    elif requires_evidence and resolution is None:
        # Older provider plain-text responses lack the structured field.
        # Do not infer a successful answer from safety acceptance alone.
        resolution = "insufficient_evidence"
    return GuardedDraft(
        text, True, None, selected, outcomes, usage, model_name,
        composed.expected_answer, resolution,
    )
