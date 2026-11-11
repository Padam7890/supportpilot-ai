"""Safe responses when assigned knowledge and integration evidence are absent."""

from dataclasses import dataclass

from app.features.ai.application.conversation_orchestration import (
    playground_missing_knowledge_reply,
)
from app.services.widget_ai import widget_missing_knowledge_reply


@dataclass(frozen=True)
class MissingEvidenceReply:
    draft: str
    reply_status: str
    safe_summary: str
    outcomes: list[dict]


def plan_missing_evidence_reply(
    *,
    execution_kind: str,
    question: str,
    clarification: str | None = None,
    intent_router_outcome: dict | None = None,
    delivery_status: str = "sent",
) -> MissingEvidenceReply:
    """Never invent store facts when no authorized evidence was retrieved."""
    knowledge_outcome = {
        "tool": "tenant_knowledge_search",
        "status": "completed",
        "result_count": 0,
    }
    if execution_kind == "widget_reply":
        return MissingEvidenceReply(
            draft=clarification or widget_missing_knowledge_reply(question),
            reply_status=delivery_status if clarification else "escalated",
            safe_summary=(
                "The shopper was asked for clarification after no matching sources were found."
                if clarification else
                "No matching knowledge was found in the active bot’s assigned sources. "
                "The shopper received a safe next step."
            ),
            outcomes=[
                *([intent_router_outcome] if intent_router_outcome else []),
                knowledge_outcome,
            ],
        )
    return MissingEvidenceReply(
        draft=playground_missing_knowledge_reply(question),
        reply_status="sent",
        safe_summary=(
            "No matching knowledge was found in the active bot’s assigned sources; "
            "no model answer was generated."
        ),
        outcomes=[knowledge_outcome],
    )
