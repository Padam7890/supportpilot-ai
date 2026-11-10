"""Build bounded, role-normalized context without treating history as evidence."""

import re

from app.features.ai.application.conversation_agent_contracts import (
    AgentInput,
    ConversationTurn,
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_VERIFIED_ORDER_PREFIXES = ("i checked your verified order ", "i verified order ", "i verified your order ")


def _model_text(value: str) -> str:
    return _EMAIL.sub("[email removed]", value.strip())[:1200]


def build_agent_input(
    message: str,
    transcript: list[dict[str, str]],
    *,
    channel: str,
) -> AgentInput:
    """Normalize existing widget/playground sender conventions.

    History is untrusted conversation text. Identity, permissions and store
    facts must come from server-owned state and tool results, not this input.
    """
    turns: list[ConversationTurn] = []
    for item in transcript[-24:]:
        sender = item.get("sender")
        if sender in {"customer", "user"}:
            role = "customer"
        elif sender == "assistant":
            role = "assistant"
        else:
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "assistant" and content.strip().casefold().startswith(_VERIFIED_ORDER_PREFIXES):
            continue
        turns.append(ConversationTurn(sender=role, content=_model_text(content)))
    normalized_message = _model_text(message)
    if (
        turns
        and turns[-1].sender == "customer"
        and turns[-1].content == normalized_message
    ):
        turns.pop()
    return AgentInput(
        message=normalized_message,
        history=turns[-12:],
        channel=channel,
    )
