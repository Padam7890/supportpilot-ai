"""Tenant-scoped, deduplicated knowledge gap occurrences."""
import uuid
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class KnowledgeGap(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_message_id", name="uq_knowledge_gap_source"),
        ForeignKeyConstraint(
            ["organization_id", "source_message_id"],
            ["messages.organization_id", "messages.id"],
            ondelete="CASCADE",
            name="fk_knowledge_gap_org_message",
        ),
        Index("ix_knowledge_gaps_org_created", "organization_id", "created_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
