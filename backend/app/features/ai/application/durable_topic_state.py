"""Durable conversation topic state with tenant-scoped compare-and-swap writes.

This stores topic labels only, never transcript, OTP, order ID or identity proof.
Callers must set the tenant DB context before using the repository.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, String, Uuid, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_ALLOWED = frozenset({"refund", "delivery", "order", "product", "payment"})
_TTL = timedelta(hours=24)


class ConversationTopicState(Base):
    __tablename__ = "conversation_topic_states"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_topic_state_version"),
        CheckConstraint("active_topic IN ('refund','delivery','order','product','payment')", name="ck_topic_state_topic"),
        Index("ix_topic_state_org_expiry", "organization_id", "expires_at"),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_topic_state_org_conversation",
        ),
        ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            ondelete="RESTRICT",
            name="fk_topic_state_org_agent",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    ai_agent_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    active_topic: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


async def read_topic_state(
    db: AsyncSession, *, organization_id: UUID, conversation_id: UUID, agent_id: UUID
) -> ConversationTopicState | None:
    return await db.scalar(
        select(ConversationTopicState).where(
            ConversationTopicState.organization_id == organization_id,
            ConversationTopicState.conversation_id == conversation_id,
            ConversationTopicState.ai_agent_id == agent_id,
            ConversationTopicState.expires_at > datetime.now(UTC),
        )
    )


async def save_topic_state(
    db: AsyncSession, *, organization_id: UUID, conversation_id: UUID,
    agent_id: UUID, topic: str, expected_version: int | None
) -> bool:
    """Insert only if absent, or update exactly the observed version.

    Returns False on concurrent modification; caller should re-read and decide.
    Transaction commit is owned by the caller.
    """
    if topic not in _ALLOWED:
        raise ValueError("Unsupported conversation topic")
    now = datetime.now(UTC)
    expiry = now + _TTL
    if expected_version is None:
        stmt = insert(ConversationTopicState).values(
            organization_id=organization_id,
            conversation_id=conversation_id,
            ai_agent_id=agent_id,
            active_topic=topic,
            version=1,
            updated_at=now,
            expires_at=expiry,
        ).on_conflict_do_nothing(index_elements=["organization_id", "conversation_id"])
    else:
        stmt = (
            update(ConversationTopicState)
            .where(
                ConversationTopicState.organization_id == organization_id,
                ConversationTopicState.conversation_id == conversation_id,
                ConversationTopicState.ai_agent_id == agent_id,
                ConversationTopicState.version == expected_version,
            )
            .values(active_topic=topic, version=expected_version + 1, updated_at=now, expires_at=expiry)
        )
    result = await db.execute(stmt)
    return bool(result.rowcount)
