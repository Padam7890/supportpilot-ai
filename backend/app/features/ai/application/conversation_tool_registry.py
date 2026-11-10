"""Constrain model-proposed tools to server-approved capabilities.

This registry is deliberately side-effect-free. Execution adapters must
separately enforce tenant ownership, customer verification, and permissions.
"""

from dataclasses import dataclass

from app.features.ai.application.conversation_tool_contracts import ToolName, ToolRequest


@dataclass(frozen=True)
class ToolCapability:
    name: ToolName
    requires_customer_verification: bool = False
    side_effecting: bool = False


CAPABILITIES: dict[ToolName, ToolCapability] = {
    ToolName.KNOWLEDGE_SEARCH: ToolCapability(ToolName.KNOWLEDGE_SEARCH),
    ToolName.CATALOG_SEARCH: ToolCapability(ToolName.CATALOG_SEARCH),
    ToolName.ORDER_LOOKUP: ToolCapability(
        ToolName.ORDER_LOOKUP, requires_customer_verification=True
    ),
    ToolName.SUPPORT_HANDOFF: ToolCapability(
        ToolName.SUPPORT_HANDOFF, side_effecting=True
    ),
}


def authorize_tool_request(
    request: ToolRequest,
    *,
    allowed_tools: frozenset[ToolName],
    customer_verified: bool = False,
    allow_side_effects: bool = False,
) -> ToolCapability:
    """Enforce an explicit server-side allowlist, not model-declared authority."""
    capability = CAPABILITIES[request.name]
    if request.name not in allowed_tools:
        raise PermissionError("Tool is not enabled for this conversation")
    if capability.requires_customer_verification and not customer_verified:
        raise PermissionError("Customer verification is required")
    if capability.side_effecting and not allow_side_effects:
        raise PermissionError("Side-effecting tool requires explicit authorization")
    return capability
