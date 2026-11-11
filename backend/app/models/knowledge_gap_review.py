"""Audit records linking approved FAQ documents to their source questions."""
import uuid
from sqlalchemy import ForeignKeyConstraint, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey

class KnowledgeGapReview(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "knowledge_gap_reviews"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "gap_id"], ["knowledge_gaps.organization_id", "knowledge_gaps.id"], ondelete="CASCADE", name="fk_gap_review_gap"),
        ForeignKeyConstraint(["organization_id", "document_id"], ["knowledge_documents.organization_id", "knowledge_documents.id"], ondelete="RESTRICT", name="fk_gap_review_document"),
        ForeignKeyConstraint(["organization_id", "reviewer_id"], ["users.organization_id", "users.id"], name="fk_gap_review_reviewer"),
        Index("ix_gap_reviews_org_gap", "organization_id", "gap_id"),
        UniqueConstraint("organization_id", "gap_id", name="uq_gap_review_single_publication"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    gap_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_ingestion")
