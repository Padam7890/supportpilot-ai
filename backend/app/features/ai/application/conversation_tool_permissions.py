"""Translate stored bot capabilities into the new agent's read-only tool names.

Only exact, known legacy capability names are accepted. Unknown or malformed
entries grant nothing. Never map order, refund or handoff capabilities here.
"""

from collections.abc import Iterable

from app.features.ai.application.conversation_tool_contracts import ToolName


_LEGACY_READ_ONLY_CAPABILITIES: dict[str, ToolName] = {
    "recommend_products": ToolName.CATALOG_SEARCH,
    "catalog_search": ToolName.CATALOG_SEARCH,
    "knowledge_search": ToolName.KNOWLEDGE_SEARCH,
}


def map_agent_tool_permissions(
    stored_tools: Iterable[str] | None,
) -> frozenset[ToolName]:
    if stored_tools is None:
        return frozenset()
    allowed: set[ToolName] = set()
    for raw in stored_tools:
        if not isinstance(raw, str):
            continue
        capability = _LEGACY_READ_ONLY_CAPABILITIES.get(raw)
        if capability is not None:
            allowed.add(capability)
    return frozenset(allowed)
