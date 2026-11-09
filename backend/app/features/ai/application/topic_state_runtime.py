"""Runtime integration for tenant-scoped durable topic context.

The durable record is a routing hint only. It cannot prove identity, authorize
commerce actions, or supply factual store policy.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai.application.conversation_memory import derive_topic_memory
from app.features.ai.application.durable_topic_state import read_topic_state, save_topic_state
from app.features.ai.application.retrieval import is_contextual_follow_up

TOPIC_WORDS = frozenset({"refund", "delivery", "order", "product", "payment"})


async def resolve_and_record_topic(
    db: AsyncSession,
    *,
    organization_id: UUID,
    conversation_id: UUID,
    agent_id: UUID,
    message: str,
    prior_transcript: list[dict[str, str]],
    retrieval_query: str,
    explicit_topic: bool,
) -> str:
    """Persist explicit subjects; recover only genuinely unanchored follow-ups.

    Call in a transaction with set_tenant_context already applied. The caller
    commits. Failure must be handled by the caller's existing retry mechanism.
    """
    current = derive_topic_memory([{"sender": "customer", "content": message}])
    state = await read_topic_state(
        db, organization_id=organization_id, conversation_id=conversation_id,
        agent_id=agent_id,
    )
    if explicit_topic and current.active_topic in TOPIC_WORDS:
        if state is None or state.active_topic != current.active_topic:
            await save_topic_state(
                db, organization_id=organization_id, conversation_id=conversation_id,
                agent_id=agent_id, topic=current.active_topic,
                expected_version=state.version if state else None,
            )
        return retrieval_query

    # A recent explicit topic is more reliable than a persisted hint.
    recent = derive_topic_memory(prior_transcript)
    if recent.active_topic is not None:
        return retrieval_query
    if state is None:
        return retrieval_query
    normalized = " ".join(message.split())[:1000]
    if not (is_contextual_follow_up(normalized) or
            (normalized.lower().split(" ", 1)[0] in {"for", "in", "to"}
             and len(normalized.split()) <= 4)):
        return retrieval_query
    # Do not concatenate raw earlier customer messages or sensitive data.
    return f"{state.active_topic} {normalized}"[:2000]
