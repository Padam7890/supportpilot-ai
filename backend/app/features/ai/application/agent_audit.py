"""Safe audit recording for tenant-owned AI bot configuration changes."""

from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIAgent, AIAgentAudit

AgentAuditEvent = Literal[
    "created",
    "updated",
    "knowledge_bases_changed",
    "activated",
    "deactivated",
]

_EVENT_FIELDS: dict[AgentAuditEvent, frozenset[str]] = {
    "created": frozenset({"name", "knowledge_base_ids", "allowed_tools"}),
    "updated": frozenset(
        {
            "changed_fields",
            "previous_name",
            "name",
            "system_instructions_changed",
            "previous_allowed_tools",
            "allowed_tools",
            "previous_knowledge_base_ids",
            "knowledge_base_ids",
            "is_default",
            "default_agent_id",
            "previous_default_agent_id",
        }
    ),
    "knowledge_bases_changed": frozenset(
        {"previous_knowledge_base_ids", "knowledge_base_ids"}
    ),
    "activated": frozenset({"status"}),
    "deactivated": frozenset({"status"}),
}

_ALLOWED_TOOLS = frozenset({"recommend_products", "compare_products"})
_ALLOWED_CHANGED_FIELDS = frozenset(
    {"name", "system_instructions", "allowed_tools", "knowledge_base_ids", "is_default"}
)
_OPTIONAL_FIELDS = frozenset(
    {
        "previous_name",
        "name",
        "previous_allowed_tools",
        "allowed_tools",
        "previous_knowledge_base_ids",
        "knowledge_base_ids",
        "default_agent_id",
        "previous_default_agent_id",
    }
)


def _validate_agent_audit_details(
    event_type: AgentAuditEvent,
    details: dict[str, object],
) -> dict[str, object]:
    """Reject unbounded or sensitive values before adding audit data to a transaction."""
    if len(details) > 11 or not set(details).issubset(_EVENT_FIELDS[event_type]):
        raise ValueError("AI bot audit details contain unsupported fields")

    safe: dict[str, object] = {}
    for key, value in details.items():
        if value is None and key in _OPTIONAL_FIELDS:
            safe[key] = None
        elif key == "changed_fields":
            if (
                not isinstance(value, list)
                or len(value) > len(_ALLOWED_CHANGED_FIELDS)
                or any(not isinstance(item, str) or item not in _ALLOWED_CHANGED_FIELDS for item in value)
            ):
                raise ValueError("AI bot audit changed fields are invalid")
            safe[key] = list(dict.fromkeys(value))
        elif key == "system_instructions_changed" or key == "is_default":
            if type(value) is not bool:
                raise ValueError("AI bot audit flag is invalid")
            safe[key] = value
        elif key in {"knowledge_base_ids", "previous_knowledge_base_ids"}:
            if not isinstance(value, list) or len(value) > 50:
                raise ValueError("AI bot audit knowledge-base list is invalid")
            safe[key] = [str(UUID(item)) for item in value if isinstance(item, str)]
            if len(safe[key]) != len(value):
                raise ValueError("AI bot audit knowledge-base identifier is invalid")
        elif key in {"allowed_tools", "previous_allowed_tools"}:
            if (
                not isinstance(value, list)
                or len(value) > len(_ALLOWED_TOOLS)
                or any(not isinstance(item, str) or item not in _ALLOWED_TOOLS for item in value)
            ):
                raise ValueError("AI bot audit tool list is invalid")
            safe[key] = list(dict.fromkeys(value))
        elif key in {"default_agent_id", "previous_default_agent_id"}:
            if not isinstance(value, str):
                raise ValueError("AI bot audit identifier is invalid")
            safe[key] = str(UUID(value))
        elif key in {"name", "previous_name"}:
            if not isinstance(value, str) or not value.strip() or len(value) > 120:
                raise ValueError("AI bot audit name is invalid")
            safe[key] = value
        elif key == "status":
            if value not in {"active", "inactive"}:
                raise ValueError("AI bot audit status is invalid")
            safe[key] = value
        else:
            raise ValueError("AI bot audit metadata is invalid")
    return safe


def record_agent_audit(
    db: AsyncSession,
    *,
    agent: AIAgent,
    actor_id: UUID,
    event_type: AgentAuditEvent,
    details: dict[str, object],
) -> None:
    """Record bounded configuration metadata; never persist bot instructions."""
    safe_details = _validate_agent_audit_details(event_type, details)
    db.add(
        AIAgentAudit(
            organization_id=agent.organization_id,
            ai_agent_id=agent.id,
            actor_user_id=actor_id,
            event_type=event_type,
            config_version=agent.config_version,
            details=safe_details,
        )
    )
