"""Compose and verify one complete reply before persistence or delivery."""

import re
import time
from dataclasses import dataclass
from typing import Any

from app.features.ai.application.conversation_context_builder import build_agent_input
from app.features.ai.application.conversation_response_composer import compose_natural_answer
from app.features.ai.application.conversation_response_evidence import knowledge_evidence
from app.features.ai.application.conversation_verified_order_evidence import AuthorizedOrderSnapshot
from app.features.ai.application.generation_metrics import log_generation_metrics
from app.features.ai.application.semantic_claim_verifier import verify_candidate

_SOURCE_MARKER = re.compile(r"\[(?:source|doc)\s*:?\s*(\d+)\]", re.IGNORECASE)
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
        return GuardedDraft(
            _SAFE_FALLBACK, False, "no_verified_evidence", [],
            [*outcomes, {"tool": "claim_grounding", "status": "blocked", "reason": "no_verified_evidence"}],
            {}, None,
        )
    composed = await compose_natural_answer(
        build_agent_input(question, transcript, channel=execution_kind),
        evidence,
        instructions=instructions,
    )
    verification = await verify_candidate(composed.text, evidence)
    usage = {
        key: composed.usage.get(key, 0) + verification.usage.get(key, 0)
        for key in composed.usage.keys() | verification.usage.keys()
    }
    model_name = composed.model_name[:120] if composed.model_name else None
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
        },
    ]
    if not verification.accepted:
        text = f"{order_text}\n\n{_SAFE_FALLBACK}" if order_text else _SAFE_FALLBACK
        return GuardedDraft(text, False, verification.reason, [], outcomes, usage, model_name)

    available = {(str(c["document_id"]), c["chunk_index"]): c for c in citations}
    selected = []
    for index in verification.source_indices:
        item = evidence.items[index - 1]
        citation = available.get((item.source_id, item.chunk_index))
        if citation is None:
            return GuardedDraft(
                _SAFE_FALLBACK, False, "missing_source_provenance", [], outcomes, usage, model_name,
            )
        selected.append(citation)
    remap = {index: position for position, index in enumerate(verification.source_indices, 1)}
    text = _SOURCE_MARKER.sub(lambda match: f"[source {remap[int(match[1])]}]", composed.text)
    if order_text:
        text = f"{order_text}\n\n{text}"
    return GuardedDraft(text, True, None, selected, outcomes, usage, model_name)
