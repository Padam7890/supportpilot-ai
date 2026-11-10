"""Privacy boundaries for provisional AI streaming context.

This module is deliberately pure: it cannot fetch data or authorize streaming.
Passing this filter is not permission to publish model tokens; downstream
source authorization and claim validation remain mandatory.
"""

from app.features.ai.application.conversational_intents import widget_conversational_reply
from app.features.ai.application.retrieval import is_contextual_follow_up


def can_stream_transcript(transcript: list[dict[str, str]]) -> bool:
    """Exclude prior staff replies and assistant turns that may contain order facts."""
    previous_social_reply = None
    for turn in transcript:
        sender, content = turn.get("sender"), turn.get("content", "")
        if sender == "customer":
            social = widget_conversational_reply(content)
            previous_social_reply = social[0] if social else None
        elif sender != "assistant" or previous_social_reply != content:
            return False
        else:
            previous_social_reply = None
    return True


def stream_conversation_context(
    question: str, transcript: list[dict[str, str]],
) -> list[dict[str, str]] | None:
    if can_stream_transcript(transcript):
        return transcript
    if is_contextual_follow_up(question):
        # A reference can depend on an earlier reply with private order data.
        return None
    # Standalone turns already have the current question and authorized sources.
    # Do not send historical assistant or staff content to a provisional reply.
    return []


