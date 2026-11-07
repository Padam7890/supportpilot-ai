"""Small deterministic Playground turns that do not need document retrieval."""

import re


_GREETING = re.compile(
    r"^(?:hi|hello|hey|namaste|नमस्ते|नमस्कार)(?: there| everyone)?[!. ,]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"^(?:thanks|thank you|thx|धन्यवाद|धन्यबाद)(?: so much| a lot| there)?[!. ,]*$",
    re.IGNORECASE,
)
_CAPABILITIES = re.compile(
    r"^(?:what can you do|how can you help|what can you help with|"
    r"तपाईं के गर्न सक्नुहुन्छ|तपाईं कसरी मद्दत गर्न सक्नुहुन्छ)[?.! ]*$",
    re.IGNORECASE,
)


def playground_conversational_reply(question: str) -> tuple[str, str] | None:
    """Answer standalone greetings and capability questions without an LLM call."""
    normalized = question.strip()
    if _GREETING.fullmatch(normalized):
        return (
            "Hi! Ask me a question and I’ll look for an answer in this bot’s assigned knowledge sources.",
            "greeting",
        )
    if _THANKS.fullmatch(normalized):
        return ("You’re welcome! Send another question whenever you’re ready.", "thanks")
    if _CAPABILITIES.fullmatch(normalized):
        return (
            "This Playground checks the selected bot against its assigned knowledge sources. "
            "I’ll use verified passages when they cover your question and say when they don’t.",
            "capabilities",
        )
    return None
