"""Read-only capability mapping regression scenarios."""

from app.features.ai.application.conversation_tool_contracts import ToolName
from app.features.ai.application.conversation_tool_permissions import map_agent_tool_permissions


def test_missing_snapshot_grants_no_tools() -> None:
    assert map_agent_tool_permissions(None) == frozenset()


def test_known_legacy_catalog_permission_maps_exactly() -> None:
    assert map_agent_tool_permissions(["recommend_products"]) == frozenset(
        {ToolName.CATALOG_SEARCH}
    )


def test_unknown_and_sensitive_capabilities_never_grant_agent_tools() -> None:
    assert map_agent_tool_permissions(
        ["refund_order", "order_lookup", "support_handoff", "READ_PRODUCTS", "", 123]
    ) == frozenset()


def test_duplicate_read_only_capabilities_are_deduplicated() -> None:
    assert map_agent_tool_permissions(
        ["catalog_search", "recommend_products", "knowledge_search"]
    ) == frozenset({ToolName.CATALOG_SEARCH, ToolName.KNOWLEDGE_SEARCH})
