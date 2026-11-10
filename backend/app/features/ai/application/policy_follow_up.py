"""Resolve short answers to a previously asked policy-choice question.

The resulting text is a retrieval/routing query, never policy evidence.
"""
import re


_REASON = re.compile(r"^(?:it(?:'s| is| was)?\s+)?(damag(?:e|ed)|defective|faulty|broken|incorrect|wrong(?:\s+item)?|change(?:d)?\s+(?:of\s+)?mind)[.! ]*$", re.I)
_POLICY = re.compile(r"\b(return|refund|exchange|policy)\b", re.I)
_CHOICE = re.compile(r"\b(damag|defect|incorrect|wrong|change.of.mind)\b", re.I)


def resolve_policy_option(message: str, transcript: list[dict[str, str]]) -> str | None:
    """Only resolve when the immediately preceding assistant asked this choice."""
    match = _REASON.fullmatch(message.strip())
    if not match or not transcript:
        return None
    previous = transcript[-1]
    if previous.get("sender") != "assistant":
        return None
    prompt = previous.get("content", "")
    if "?" not in prompt or not _POLICY.search(prompt) and not (
        _CHOICE.search(prompt) and re.search(r"\b(return|refund)\b", " ".join(
            turn.get("content", "") for turn in transcript[-6:] if turn.get("sender") == "customer"
        ), re.I)
    ):
        return None
    reason = match.group(1).casefold()
    if reason.startswith(("damag", "broken")):
        reason = "damaged"
    elif reason in {"faulty", "defective"}:
        reason = "defective"
    elif reason.startswith(("wrong", "incorrect")):
        reason = "incorrect"
    else:
        reason = "change of mind"
    return f"What is the store return and refund policy for {reason} items?"
