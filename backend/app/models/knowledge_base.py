import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class KnowledgeBase(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_knowledge_bases_status"),
        UniqueConstraint("organization_id", "id", name="uq_knowledge_bases_org_id"),
        Index("ix_knowledge_bases_org_status", "organization_id", "status"),
        Index("uq_knowledge_bases_org_default", "organization_id", unique=True, postgresql_where=text("is_default IS TRUE")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AIAgent(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ai_agents"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_ai_agents_status"),
        CheckConstraint("config_version > 0", name="ck_ai_agents_config_version"),
        UniqueConstraint("organization_id", "id", name="uq_ai_agents_org_id"),
        Index("ix_ai_agents_org_status", "organization_id", "status"),
        Index("uq_ai_agents_org_default", "organization_id", unique=True, postgresql_where=text("is_default IS TRUE")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    system_instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(
        JSON,
        default=lambda: ["recommend_products", "compare_products"],
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    config_version: Mapped[int] = mapped_column(default=1, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AIAgentKnowledgeBase(Base):
    __tablename__ = "ai_agent_knowledge_bases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            name="fk_ai_agent_knowledge_bases_org_agent",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"],
            ["knowledge_bases.organization_id", "knowledge_bases.id"],
            name="fk_ai_agent_knowledge_bases_org_base",
            ondelete="CASCADE",
        ),
        Index("ix_ai_agent_knowledge_bases_org_base", "organization_id", "knowledge_base_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    ai_agent_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
