"""Shared guarded generation for Playground and Widget.

Never publish unvalidated model deltas. A generated answer must pass the
existing grounding policy before it can be persisted or delivered.
"""

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.features.ai.application.claim_grounding import check_generated_answer, check_grounded_claims
from app.features.ai.application.conversation_context_builder import build_agent_input
from app.features.ai.application.conversation_response_composer import compose_natural_answer
from app.features.ai.application.conversation_response_evidence import ResponseEvidence
from app.features.ai.application.generation_metrics import log_generation_metrics
from app.features.ai.application.intent_routing.deterministic import assess_deterministic_route
from app.features.ai.application.intent_routing.schemas import Intent
from app.features.ai.workflows.grounded_reply import create_grounded_draft


@dataclass(frozen=True)
class GuardedDraft:
    text: str
    accepted: bool
    grounding_reason: str | None
    citations: list
    outcomes: list
    usage: dict
    model_name: str | None


async def generate_guarded_draft(
    *,
    organization_id: UUID,
    execution_id: UUID,
    execution_kind: str,
    question: str,
    instructions: str | None,
    transcript: list[dict[str, str]],
    context: list[dict[str, str | int]],
    integration_context: dict[str, Any] | None,
    citations: list,
    outcomes: list,
    auto_reply: bool,
    correlation_id: str | None,
) -> GuardedDraft:
    started = time.monotonic()
    # All non-integration turns use the canonical natural-answer composer.
    # Provider-specific commerce generation remains isolated until authorized
    # Shopify facts can be supplied as typed, verified evidence.
    use_canonical_composer = not integration_context and execution_kind in {
        "widget_reply", "playground", "reply_draft",
    }
    grounding_sources: list[dict[str, str]] = []
    if use_canonical_composer:
        evidence_items = [
            {
                "source": "knowledge_search",
                "content": str(item.get("excerpt") or item.get("content") or "")[:1200],
            }
            for item in context[:6]
        ]
        evidence_items = [item for item in evidence_items if item["content"].strip()]
        grounding_sources = [{"excerpt": item["content"]} for item in evidence_items]
        route = assess_deterministic_route(question, [])
        needs_verified_facts = (
            route.requires_tools
            or route.requires_knowledge
            or route.intent in {Intent.PRODUCT, Intent.ORDER, Intent.REFUND}
        )
        if not evidence_items and needs_verified_facts:
            return GuardedDraft(
                text=(
                    "I couldn't verify that store-specific information. "
                    "Please contact our support team for confirmation."
                ),
                accepted=False,
                grounding_reason="no_verified_evidence",
                citations=[],
                outcomes=[
                    *outcomes,
                    {"tool": "claim_grounding", "status": "blocked",
                     "reason": "no_verified_evidence"},
                ],
                usage={},
                model_name=None,
            )
        composed = await compose_natural_answer(
            build_agent_input(
                question, transcript,
                channel="widget" if execution_kind == "widget_reply" else "playground",
            ),
            ResponseEvidence(
                context=evidence_items,
                source_ids=[],
                answerable=bool(evidence_items),
                unavailable=not bool(evidence_items),
            ),
            instructions=instructions,
        )
        result = {
            "draft": composed.text,
            "usage": composed.usage,
            "model_name": composed.model_name,
        }
    else:
        result = await create_grounded_draft(
            organization_id=organization_id,
            execution_id=execution_id,
            question=question,
            instructions=instructions,
            conversation_context=[
                {"sender": turn["sender"], "content": turn["content"]}
                for turn in transcript
            ],
            knowledge_context=context,
            integration_context=integration_context,
            auto_reply=auto_reply,
        )
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    raw_model_name = result.get("model_name")
    model_name = raw_model_name[:120] if isinstance(raw_model_name, str) and raw_model_name else None
    log_generation_metrics(
        execution_id=str(execution_id),
        execution_kind=execution_kind,
        model_name=result.get("model_name")
        if isinstance(result.get("model_name"), str) else None,
        started_monotonic=started,
        usage=usage,
        streamed=False,
        correlation_id=correlation_id,
    )
    generated = str(result.get("draft", ""))[:12000]
    # Validate the same bounded excerpts actually supplied to the composer.
    # Integration context must not disable knowledge claim validation.
    # The specialized integration path remains responsible for authorization.
    grounding = (
        check_grounded_claims(
            generated, grounding_sources, require_citations=True,
        )
        if use_canonical_composer and grounding_sources
        else check_generated_answer(
            generated, context
        )
    )
    if grounding.accepted:
        return GuardedDraft(
            text=generated, accepted=True, grounding_reason=None,
            citations=citations, outcomes=outcomes, usage=usage,
            model_name=model_name,
        )
    return GuardedDraft(
        text=(
            "I couldn't verify the details in the available knowledge sources. "
            "Please contact our support team to confirm."
        ),
        accepted=False,
        grounding_reason=grounding.reason,
        citations=[],
        outcomes=[
            *outcomes,
            {
                "tool": "claim_grounding",
                "status": "blocked",
                "reason": grounding.reason,
            },
        ],
        usage=usage,
        model_name=model_name,
    )
