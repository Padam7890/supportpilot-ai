"""Compose and verify one complete reply before persistence or delivery."""

import logging
import time
from dataclasses import dataclass
from typing import Any

from app.features.ai.application.claim_grounding import CITATION_PATTERN, check_grounded_claims
from app.features.ai.application.conversation_context_builder import build_agent_input
from app.features.ai.application.conversation_response_composer import compose_natural_answer
from app.features.ai.application.conversation_response_evidence import knowledge_evidence
from app.features.ai.application.conversation_verified_order_evidence import AuthorizedOrderSnapshot
from app.features.ai.application.generation_metrics import log_generation_metrics
from app.features.ai.application.semantic_claim_verifier import verify_candidate
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
            {}, None,
        )
    agent_input = build_agent_input(question, transcript, channel=execution_kind)
    usage: dict[str, int] = {}
    model_name: str | None = None
    verification = None
    composed = None
    for attempt in range(1):
        # One bounded repair attempt. The retry receives only the same verified
        # evidence, never new sources, order snapshots or model-created facts.
        repair_instruction = (
            "\\nGrounding repair: Your previous answer was rejected by the verifier "
            "for reason " + verification.reason + ". Rewrite the answer from scratch "
            "using ONLY explicit facts in the provided evidence. Cite each factual "
            "sentence with [source N] immediately before its final punctuation. "
            "Keep exact numbers, units, exclusions and conditions. Do not invent "
            "policies, eligibility or actions. If the evidence cannot answer the "
            "question, say so without asserting unsupported store facts."
            if attempt and verification is not None else ""
        )
        composed = await compose_natural_answer(
            agent_input, evidence,
            instructions=(instructions or "") + repair_instruction,
        )
        try:
            verification = await verify_candidate(composed.text, evidence)
        except AIProviderError as exc:
            if exc.code != "execution_token_budget_exceeded":
                raise
            logger.info("rag_grounding_debug execution_id=%s stage=verification_budget_exhausted", execution_id)
            return GuardedDraft(_SAFE_FALLBACK, False, "verification_budget_exhausted", [], outcomes, usage, model_name)
        for key in composed.usage.keys() | verification.usage.keys():
            usage[key] = usage.get(key, 0) + composed.usage.get(key, 0) + verification.usage.get(key, 0)
        model_name = composed.model_name[:120] if composed.model_name else model_name
        logger.info(
            "rag_grounding_debug execution_id=%s stage=verification attempt=%d "
            "accepted=%s reason=%s evidence_count=%d",
            execution_id, attempt + 1, verification.accepted,
            verification.reason, len(evidence.items),
        )
        if not verification.accepted and verification.reason == "missing_citations" and len(evidence.items) == 1:
            # Citation-only repair: attach the sole source to each uncited
            # factual span. Never treat this as proof of entailment: the
            # complete candidate is reviewed again, including semantic checks.
            from app.features.ai.application.semantic_claim_verifier import _SPAN_BREAK
            segments = [part.strip() for part in _SPAN_BREAK.split(composed.text) if part.strip()]
            repaired = []
            for segment in segments:
                if CITATION_PATTERN.search(segment):
                    repaired.append(segment)
                elif segment.endswith(("?", "？")):
                    repaired.append(segment)
                else:
                    repaired.append(segment + " [source 1]")
            candidate = "\n".join(repaired)
            source = [{"index": 1, "excerpt": evidence.items[0].content}]
            lexical = check_grounded_claims(candidate, source, require_citations=True)
            if lexical.accepted:
                try:
                    repaired_verification = await verify_candidate(candidate, evidence)
                except AIProviderError as exc:
                    if exc.code != "execution_token_budget_exceeded":
                        raise
                    logger.info("rag_grounding_debug execution_id=%s stage=citation_repair_budget_exhausted", execution_id)
                    break
                for key, value in repaired_verification.usage.items():
                    usage[key] = usage.get(key, 0) + value
                logger.info(
                    "rag_grounding_debug execution_id=%s stage=citation_repair accepted=%s reason=%s",
                    execution_id, repaired_verification.accepted, repaired_verification.reason,
                )
                if repaired_verification.accepted:
                    composed = type(composed)(text=candidate, usage=composed.usage, model_name=composed.model_name)
                    verification = repaired_verification
        if verification.accepted:
            break
        # Sensitive or contradictory claims should not be retried as routine
        # citation repairs. Keep the existing safe fallback.
        if verification.reason in {"sensitive_claim", "contradicted_claim"}:
            break
    assert composed is not None and verification is not None
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
        text = f"{order_text}\\n\\n{_SAFE_FALLBACK}" if order_text else _SAFE_FALLBACK
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
    # Keep verified provenance in structured citations, not customer-visible text.
    # Strip only after verification and provenance checks have succeeded.
    text = CITATION_PATTERN.sub("", composed.text)
    # The model may emit escaped paragraph separators as literal characters.
    # Normalize only newline escapes after the factual answer is verified.
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if order_text:
        text = f"{order_text}\n\n{text}"
    return GuardedDraft(text, True, None, selected, outcomes, usage, model_name)
