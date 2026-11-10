"""Opt-in conversation orchestration with injected model decision and tools.

No live worker integration here. Model-selected actions are constrained to
read-only tools; authorization is always enforced by the tool executor.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from app.features.ai.application.conversation_agent_contracts import (
    AgentDecision, AgentInput,
)
from app.features.ai.application.conversation_response_composer import (
    ComposedAnswer, compose_natural_answer,
)
from app.features.ai.application.conversation_response_evidence import (
    ResponseEvidence, compose_response_evidence,
)
from app.features.ai.application.conversation_tool_contracts import (
    ToolName, ToolRequest,
)
from app.features.ai.application.conversation_tool_executor import (
    ToolAdapter, ToolExecutionContext, execute_agent_tools,
)
from app.features.ai.application.claim_grounding import check_grounded_claims


@dataclass(frozen=True)
class AgentRunResult:
    answer: str
    source_ids: list[str]
    tool_names: list[str]
    usage: dict[str, int]
    model_name: str | None


AgentPlanner = Callable[[AgentInput], Awaitable[AgentDecision]]
AnswerComposer = Callable[[AgentInput, ResponseEvidence], Awaitable[ComposedAnswer]]
_READ_ONLY = frozenset({ToolName.KNOWLEDGE_SEARCH, ToolName.CATALOG_SEARCH})


async def run_conversation_agent(
    agent_input: AgentInput,
    *,
    planner: AgentPlanner,
    adapters: Mapping[ToolName, ToolAdapter],
    composer: AnswerComposer = compose_natural_answer,
) -> AgentRunResult:
    """Run a single bounded turn, without granting model-generated permissions."""
    decision = await planner(agent_input)
    if decision.response_mode == "handoff":
        raise PermissionError("Handoff must use the existing authorized workflow")
    if decision.response_mode == "tool" and not decision.tool_requests:
        raise ValueError("Tool mode requires tool requests")
    if decision.response_mode != "tool" and decision.tool_requests:
        raise ValueError("Tool requests are only valid in tool mode")
    if decision.response_mode == "clarify":
        if not decision.clarification:
            raise ValueError("Clarification requires a question")
        return AgentRunResult(
            answer=decision.clarification, source_ids=[], tool_names=[],
            usage={}, model_name=None,
        )

    requests: list[ToolRequest] = decision.tool_requests
    if any(request.name not in _READ_ONLY for request in requests):
        raise PermissionError("Only read-only tools are supported by this agent")
    results = await execute_agent_tools(
        requests,
        context=ToolExecutionContext(allowed_tools=_READ_ONLY),
        adapters=adapters,
    ) if requests else []
    evidence = compose_response_evidence(results)
    if requests and not evidence.answerable:
        raise ValueError("No verified tool evidence available for requested store facts")
    composed = await composer(agent_input, evidence)
    if evidence.answerable:
        # Conservative numeric and citation checks; not semantic entailment.
        checked = check_grounded_claims(
            composed.text,
            [{"excerpt": item["content"]} for item in evidence.context],
            require_citations=False,
        )
        if not checked.accepted:
            raise ValueError(f"Generated answer failed grounding: {checked.reason}")
    return AgentRunResult(
        answer=composed.text,
        source_ids=evidence.source_ids,
        tool_names=[request.name.value for request in requests],
        usage=composed.usage,
        model_name=composed.model_name,
    )
