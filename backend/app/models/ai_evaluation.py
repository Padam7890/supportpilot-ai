import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKey


class AIEvaluation(UUIDPrimaryKey, Base):
    """Private teammate feedback on a completed AI reply draft."""

    __tablename__ = "ai_evaluations"
    __table_args__ = (
        CheckConstraint("rating IN ('helpful', 'not_helpful')", name="ck_ai_evaluations_rating"),
        CheckConstraint(
            "category IS NULL OR category IN ('accuracy', 'grounding', 'relevance', 'tone')",
            name="ck_ai_evaluations_category",
        ),
        UniqueConstraint("organization_id", "execution_id", "evaluator_user_id", name="uq_ai_evaluations_execution_evaluator"),
        ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["ai_executions.organization_id", "ai_executions.id"],
            name="fk_ai_evaluations_org_execution",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evaluator_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ai_evaluations_org_user",
            ondelete="RESTRICT",
        ),
        Index("ix_ai_evaluations_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evaluator_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
