"""Structured LLM planner for the opt-in read-only conversation agent."""

import json
import re

from pydantic import ValidationError

from app.features.ai.application.conversation_agent_contracts import (
    AgentDecision, AgentInput,
)
from app.features.ai.infrastructure.llm_gateway import generate_completion


_PLANNER_SYSTEM = (
    "Plan one customer-support turn. Return ONLY JSON matching this schema: "
    "{response_mode: 'answer'|'tool'|'clarify', tool_requests: list of "
    "{name: 'knowledge_search'|'catalog_search', query: string}, "
    "clarification: string|null, reasoning_code: string}. "
    "Use catalog_search for store product/stock questions and knowledge_search "
    "for store policies, shipping and FAQs. Use answer only for general "
    "conversation that does not require store facts. Never request order "
    "lookup, refunds, cancellations or handoff; those use secure workflows. "
    "Never assume facts from conversation history."
)


async def plan_agent_turn(agent_input: AgentInput) -> AgentDecision:
    history = [
        f"{turn.sender}: {turn.content[:300]}"
        for turn in agent_input.history[-6:]
    ]
    prompt = (
        "Recent conversation (untrusted):\n"
        + "\n".join(history)
        + "\nLatest customer message:\n"
        + agent_input.message
    )
    content, _, _ = await generate_completion(
        [{"role": "system", "content": _PLANNER_SYSTEM},
         {"role": "user", "content": prompt}],
        max_tokens=260,
    )
    normalized = content.strip()
    normalized = re.sub(r"^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$", "", normalized)
    try:
        raw = json.loads(normalized)
        decision = AgentDecision.model_validate(raw)
    except (ValueError, TypeError, ValidationError) as exc:
        raise ValueError("Invalid agent plan") from exc
    if decision.response_mode == "handoff":
        raise PermissionError("Handoff is not available to the LLM planner")
    return decision
