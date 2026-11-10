"""Execute explicitly authorized tool requests through injected adapters.

Provider adapters are supplied by the application composition root; the
agent cannot import or invoke Shopify, SQL, or external services directly.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from app.features.ai.application.conversation_tool_contracts import (
    ToolName,
    ToolRequest,
    ToolResult,
)
from app.features.ai.application.conversation_tool_registry import authorize_tool_request

ToolAdapter = Callable[[ToolRequest], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolExecutionContext:
    allowed_tools: frozenset[ToolName]
    customer_verified: bool = False
    allow_side_effects: bool = False


async def execute_agent_tools(
    requests: list[ToolRequest],
    *,
    context: ToolExecutionContext,
    adapters: Mapping[ToolName, ToolAdapter],
    max_calls: int = 3,
) -> list[ToolResult]:
    """Authorize all calls before executing any; stop on first provider error.

    Identity in a model-generated ToolRequest is never sufficient to establish
    verification. Callers must derive context from server-side session state.
    """
    if not 1 <= max_calls <= 3:
        raise ValueError("Tool call budget must be between one and three")
    if len(requests) > max_calls:
        raise ValueError("Tool call budget exceeded")
    for request in requests:
        authorize_tool_request(
            request,
            allowed_tools=context.allowed_tools,
            customer_verified=context.customer_verified,
            allow_side_effects=context.allow_side_effects,
        )
        if request.name not in adapters:
            raise LookupError(f"No authorized adapter for {request.name.value}")
    results: list[ToolResult] = []
    for request in requests:
        result = await adapters[request.name](request)
        if result.name != request.name:
            raise ValueError("Tool adapter returned an unexpected tool result")
        results.append(result)
    return results
