from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBaseAudit

KnowledgeBaseAuditEvent = Literal[
    "created",
    "updated",
    "archived",
    "restored",
    "default_changed",
    "document_moved",
    "document_uploaded",
    "document_reprocessed",
    "document_deleted",
]

_EVENT_DETAIL_KEYS: dict[KnowledgeBaseAuditEvent, frozenset[str]] = {
    "created": frozenset({"name"}),
    "updated": frozenset({"changed_fields", "name"}),
    "archived": frozenset({"name"}),
    "restored": frozenset({"name"}),
    "default_changed": frozenset({"is_default", "new_default_id", "previous_default_id"}),
    "document_moved": frozenset(
        {"document_id", "from_knowledge_base_id", "to_knowledge_base_id"}
    ),
    "document_uploaded": frozenset({"document_id", "size_bytes", "content_type"}),
    "document_reprocessed": frozenset({"document_id"}),
    "document_deleted": frozenset({"document_id"}),
}


def _validated_audit_details(
    event_type: KnowledgeBaseAuditEvent,
    details: dict[str, object],
) -> dict[str, object]:
    """Keep audit payloads small and limited to safe identifiers and metadata."""
    allowed_keys = _EVENT_DETAIL_KEYS[event_type]
    if len(details) > 4 or not set(details).issubset(allowed_keys):
        raise ValueError("Knowledge-base audit details contain unsupported fields")

    safe_details: dict[str, object] = {}
    for key, value in details.items():
        if key == "changed_fields":
            if (
                not isinstance(value, list)
                or len(value) > 2
                or any(
                    not isinstance(item, str) or item not in {"name", "description"}
                    for item in value
                )
            ):
                raise ValueError("Knowledge-base audit changed fields are invalid")
            safe_details[key] = list(value)
            continue
        if key == "size_bytes":
            if type(value) is not int or not 1 <= value <= 20 * 1024 * 1024:
                raise ValueError("Knowledge-base audit upload size is invalid")
            safe_details[key] = value
            continue
        if key == "is_default":
            if type(value) is not bool:
                raise ValueError("Knowledge-base audit default marker is invalid")
            safe_details[key] = value
            continue
        if value is None and key in {"new_default_id", "previous_default_id"}:
            safe_details[key] = None
            continue
        if not isinstance(value, str):
            raise ValueError("Knowledge-base audit metadata must be a string")  # noqa: TRY004 - keep the audit validation error contract
        if key == "content_type":
            if value not in {"application/pdf", "text/plain", "text/markdown"}:
                raise ValueError("Knowledge-base audit content type is invalid")
            safe_details[key] = value
            continue
        max_length = 120 if key == "name" else 36
        if not value or len(value) > max_length:
            raise ValueError("Knowledge-base audit metadata is out of bounds")
        if key.endswith("_id"):
            try:
                UUID(value)
            except ValueError as exc:
                raise ValueError("Knowledge-base audit identifier is invalid") from exc
        safe_details[key] = value
    return safe_details


def record_knowledge_base_audit(
    db: AsyncSession,
    *,
    organization_id: UUID,
    knowledge_base_id: UUID,
    actor_user_id: UUID,
    event_type: KnowledgeBaseAuditEvent,
    details: dict[str, object],
) -> None:
    """Add bounded knowledge-base change metadata to the caller's transaction."""
    safe_details = _validated_audit_details(event_type, details)
    db.add(
        KnowledgeBaseAudit(
            organization_id=organization_id,
            knowledge_base_id=knowledge_base_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            details=safe_details,
        )
    )
