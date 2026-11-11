"""Idempotent storage for verified missing-knowledge signals."""
from uuid import UUID
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.ai.domain.knowledge_gap_policy import KnowledgeGapSignal
from app.models.knowledge_gap import KnowledgeGap


async def persist_knowledge_gap(db: AsyncSession, signal: KnowledgeGapSignal) -> None:
    statement = insert(KnowledgeGap).values(
        organization_id=UUID(signal.organization_id),
        source_message_id=UUID(signal.source_message_id),
        question=signal.question,
        reason=signal.reason.value,
        status="open",
    ).on_conflict_do_nothing(constraint="uq_knowledge_gap_source")
    await db.execute(statement)
