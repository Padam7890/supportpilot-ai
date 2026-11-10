"""Build bounded, role-normalized context without treating history as evidence."""

from app.features.ai.application.conversation_agent_contracts import (
    AgentInput,
    ConversationTurn,
)


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
        turns.append(ConversationTurn(sender=role, content=content.strip()[:1200]))
    normalized_message = message.strip()[:1200]
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
