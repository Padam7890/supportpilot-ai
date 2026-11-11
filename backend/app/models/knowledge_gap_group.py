"""Durable, tenant-scoped reviewer-controlled knowledge gap groups."""
import uuid

from sqlalchemy import ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class KnowledgeGapGroup(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "knowledge_gap_groups"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_knowledge_gap_groups_org_id"),
        Index("ix_knowledge_gap_groups_org", "organization_id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    representative: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")


class KnowledgeGapGroupMember(Base):
    __tablename__ = "knowledge_gap_group_members"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "group_id"], ["knowledge_gap_groups.organization_id", "knowledge_gap_groups.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["organization_id", "gap_id"], ["knowledge_gaps.organization_id", "knowledge_gaps.id"], ondelete="CASCADE"),
        UniqueConstraint("organization_id", "gap_id", name="uq_gap_group_one_membership"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    gap_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
