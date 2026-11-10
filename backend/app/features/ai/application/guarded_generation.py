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
from app.services.ai_execution import create_grounded_draft


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
    used_new_rag_composer = False
    # Knowledge-only runs now share the bounded natural-answer composer.
    # Retrieval and citation authorization remain in the existing worker.
    # Integration-backed answers keep their dedicated secure execution path.
    if (
        context
        and not integration_context
        and execution_kind in {"widget_reply", "playground", "reply_draft"}
    ):
        evidence_items = [
            {
                "source": "knowledge_search",
                "content": str(item.get("excerpt") or item.get("content") or "")[:1200],
            }
            for item in context[:6]
        ]
        evidence_items = [item for item in evidence_items if item["content"].strip()]
        if not evidence_items:
            raise ValueError("Retrieved knowledge has no usable excerpts")
        used_new_rag_composer = True
        composed = await compose_natural_answer(
            build_agent_input(
                question, transcript,
                channel="widget" if execution_kind == "widget_reply" else "playground",
            ),
            ResponseEvidence(
                context=evidence_items,
                source_ids=[],
                answerable=True,
                unavailable=False,
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
    # New RAG generation requires an explicit reference to retrieved evidence.\n    # The legacy integration path has separate trusted-data handling and is\n    # not covered by this stricter citation contract yet.\n    grounding = (\n        check_grounded_claims(generated, context, require_citations=True)\n        if used_new_rag_composer\n        else check_generated_answer(\n            generated, context if not integration_context else []\n        )\n    )
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
