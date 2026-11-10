"""Focused contract tests; execution of these tests is deferred."""

import pytest
from pydantic import ValidationError

from app.features.ai.application.conversation_agent_contracts import AgentInput
from app.features.ai.application.conversation_tool_contracts import ToolName, ToolRequest
from app.features.ai.application.conversation_tool_registry import authorize_tool_request


def test_unverified_order_lookup_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ToolRequest(name=ToolName.ORDER_LOOKUP, query="Where is order 123?")


def test_order_lookup_requires_server_verified_state() -> None:
    request = ToolRequest(
        name=ToolName.ORDER_LOOKUP,
        query="Where is my order?",
        verified_customer_id="customer-1",
        order_reference="123",
    )
    with pytest.raises(PermissionError):
        authorize_tool_request(
            request, allowed_tools=frozenset({ToolName.ORDER_LOOKUP})
        )


def test_side_effecting_handoff_requires_explicit_permission() -> None:
    request = ToolRequest(name=ToolName.SUPPORT_HANDOFF, query="Contact staff")
    with pytest.raises(PermissionError):
        authorize_tool_request(
            request, allowed_tools=frozenset({ToolName.SUPPORT_HANDOFF})
        )


def test_catalog_lookup_is_read_only_and_allowed() -> None:
    request = ToolRequest(name=ToolName.CATALOG_SEARCH, query="Samsung phones")
    capability = authorize_tool_request(
        request, allowed_tools=frozenset({ToolName.CATALOG_SEARCH})
    )
    assert capability.side_effecting is False


def test_agent_history_is_bounded() -> None:
    with pytest.raises(ValidationError):
        AgentInput(
            message="Hello",
            channel="widget",
            history=[{"sender": "customer", "content": "Hi"}] * 13,
        )
