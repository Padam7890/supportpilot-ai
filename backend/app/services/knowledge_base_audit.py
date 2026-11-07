from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBaseAudit


def record_knowledge_base_audit(
    db: AsyncSession,
    *,
    organization_id: UUID,
    knowledge_base_id: UUID,
    actor_user_id: UUID,
    event_type: str,
    details: dict[str, Any],
) -> None:
    """Add bounded knowledge-base change metadata to the caller's transaction."""
    db.add(
        KnowledgeBaseAudit(
            organization_id=organization_id,
            knowledge_base_id=knowledge_base_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            details=details,
        )
    )
