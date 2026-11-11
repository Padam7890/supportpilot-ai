"""Versioned embedding cache for unanswered customer questions."""
import uuid

from sqlalchemy import JSON, ForeignKeyConstraint, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeGapEmbedding(Base):
    __tablename__ = "knowledge_gap_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "gap_id"], ["knowledge_gaps.organization_id", "knowledge_gaps.id"], ondelete="CASCADE", name="fk_gap_embedding_org_gap"),
        Index("ix_gap_embeddings_org_model", "organization_id", "model", "version"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    gap_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    model: Mapped[str] = mapped_column(String(200), primary_key=True)
    version: Mapped[str] = mapped_column(String(60), primary_key=True)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    values: Mapped[list[float]] = mapped_column(JSON, nullable=False)
