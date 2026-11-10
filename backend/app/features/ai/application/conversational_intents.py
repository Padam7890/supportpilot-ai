"""Deterministic routing for social turns shared by Playground and the widget."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationalIntent:
    name: str
    playground_reply: str
    widget_reply: str


_GREETING = re.compile(
    r"(?:hi|hello|hey|good morning|good afternoon|good evening|"
    r"namaste|namaskar|नमस्ते|नमस्कार|नमस्तेँ|नमस्कारम्|"
    r"नमस्कार छ|धन्यवाद|नमस्ते साथी|नमस्कार साथी)"
    r"(?:\s+(?:there|everyone|friend|bro|mate))?",
    re.IGNORECASE,
)
_CASUAL = re.compile(
    r"(?:what(?:'s|s| is) up(?: there| bro| friend)?|"
    r"how are you(?: doing)?(?: today)?|how(?:'s| is) it going|"
    r"are you there|are you online|can you hear me|"
    r"kasto cha(?:u)?|sanchai chau|sanchai chhau|k cha|ke cha|"
    r"तपाईंलाई कस्तो छ|तिमीलाई कस्तो छ|कस्तो छ|सन्चै हुनुहुन्छ)",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"(?:thanks?|thank you|thx|cheers|धन्यवाद|धन्यबाद|धन्यावाद|धेरै धन्यवाद|"
    r"dhanyabad|dhanyabaad|dherai dhanyabad)"
    r"(?:\s+(?:so much|a lot|bro|there|friend|mate|dai|didi))?",
    re.IGNORECASE,
)
_GOODBYE = re.compile(
    r"(?:bye|goodbye|good bye|see you|talk to you later|फेरि भेटौँ|फेरि भेटौं|"
    r"फेरि भेटौँला|pachi bhetaula|pachi bhetaum)",
    re.IGNORECASE,
)
_CAPABILITIES = re.compile(
    r"(?:what can you do|how can you help|what can you help with|"
    r"what do you do|how does this work|"
    r"तपाईं के गर्न सक्नुहुन्छ|तपाईं कसरी मद्दत गर्न सक्नुहुन्छ)",
    re.IGNORECASE,
)
_IDENTITY = re.compile(
    r"(?:what(?:'s| is|s) your name|who are you|what are you|"
    r"are you (?:a |an )?(?:bot|ai|assistant|real person)|"
    r"तिम्रो नाम|तपाईंको नाम|तपाई को नाम|के हो तिम्रो नाम)",
    re.IGNORECASE,
)
_HELP = re.compile(
    r"(?:can you help(?: me)?(?: today| now)?|could you help(?: me)?|"
    r"i need help|help me(?: please)?|need some help|"
    r"मलाई मद्दत चाहियो|मद्दत चाहियो|सहायता चाहियो)",
    re.IGNORECASE,
)
_EMOTIONAL = re.compile(
    r"(?:i(?:'m| am) (?:frustrated|angry|upset)|this is ridiculous|"
    r"terrible experience|worst experience|not happy|very disappointed)",
    re.IGNORECASE,
)

_OFF_TOPIC = re.compile(
    r"(?:tell me (?:a |one )?joke|make me laugh|"
    r"what is the meaning of life|can you write (?:my |a )?(?:essay|poem)|"
    r"solve (?:my |this )?homework)",
    re.IGNORECASE,
)

_END_PUNCTUATION = re.compile(r"[.!?,;:]+$")


def _normalize_social_text(message: str) -> str:
    normalized = unicodedata.normalize("NFKC", message).casefold()
    normalized = normalized.replace("’", "'").replace("‘", "'")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"^[.!?,;:\s]+|[.!?,;:\s]+$", "", normalized)
    return normalized


def _strip_social_prefix(text: str) -> str:
    """Remove only social openers, leaving any substantive request visible."""
    return re.sub(
        r"^(?:(?:hi|hello|hey|good morning|good afternoon|good evening|"
        r"namaste|namaskar|नमस्ते|नमस्कार)\b\s*[,!?.\s]*)+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _social_only_pattern(pattern: re.Pattern[str], text: str) -> bool:
    direct = _END_PUNCTUATION.sub("", text).strip()
    if pattern.fullmatch(direct):
        return True
    value = _strip_social_prefix(text)
    value = _END_PUNCTUATION.sub("", value).strip()
    # A message is routed socially only when all remaining words are part of
    # the social phrase. This prevents "hey, what's your refund policy?" from
    # bypassing knowledge retrieval.
    return bool(pattern.fullmatch(value))


def classify_conversational_intent(message: str) -> ConversationalIntent | None:
    """Recognize standalone social turns; support questions continue to RAG/tools."""
    text = _normalize_social_text(message)
    if not text:
        return None

    if _social_only_pattern(_IDENTITY, text):
        return ConversationalIntent(
            "identity",
            "I'm the AI assistant for this workspace bot. I answer from assigned knowledge sources and never invent store facts.",
            "I'm this store's support assistant—a virtual helper, not a person. I can help with policies, products, and secure order lookups. "
            "What can I help you with?",
        )
    if _social_only_pattern(_HELP, text):
        return ConversationalIntent(
            "help",
            "Sure—tell me what you need and I'll search this bot's assigned knowledge sources.",
            "Absolutely! I can help with store questions, guide a secure order lookup, or connect you with the support team. What do you need?",
        )
    if _social_only_pattern(_CAPABILITIES, text):
        return ConversationalIntent(
            "capabilities",
            "I can answer questions using this bot’s assigned knowledge sources. What would you like to know?",
            "I can help find answers about this store, guide you through a secure order lookup, or pass a request "
            "to the support team. What would you like help with?",
        )
    if _social_only_pattern(_THANKS, text):
        return ConversationalIntent(
            "thanks",
            "You’re welcome! Ask me anything about the information available to this bot.",
            "You’re welcome! Is there anything else I can help you with today?",
        )
    if _social_only_pattern(_GOODBYE, text):
        return ConversationalIntent(
            "goodbye",
            "Goodbye! I’m here whenever you need help.",
            "Goodbye! Feel free to come back if you need anything else.",
        )
    if _social_only_pattern(_CASUAL, text):
        return ConversationalIntent(
            "casual",
            "Hey! I'm doing well, thanks. How can I help you today?",
            "I’m doing well, thanks for asking! What can I help you with today?",
        )
    if _social_only_pattern(_GREETING, text):
        return ConversationalIntent(
            "greeting",
            "Hey! How can I help you today? Ask me a question and I’ll check this bot’s assigned sources.",
            "Hi there! I’m your store’s support assistant. I can help with order updates, product questions, "
            "and store policies. What can I help you with?",
        )
    if _social_only_pattern(_OFF_TOPIC, text):
        return ConversationalIntent(
            "off_topic",
            "I'm focused on this bot's assigned support knowledge. Ask me a question about its sources and I'll help.",
            "I'm here to help with this store's products, policies, and orders. What can I help you find?",
        )
    if _social_only_pattern(_EMOTIONAL, text):
        return ConversationalIntent(
            "empathy",
            "I'm sorry this has been frustrating. Tell me what's going on and I'll look for answers in this bot's sources or suggest a next step.",
            "I'm sorry you're having a frustrating experience. Share what happened and I'll help where I can—or loop in a support teammate if needed.",
        )
    return None


def should_skip_knowledge_retrieval(message: str, *, channel: str) -> bool:
    """Whether a turn can skip tenant knowledge search (social-only turns)."""
    if classify_conversational_intent(message) is not None:
        return True
    if channel == "playground":
        return False
    return False


def playground_conversational_reply(question: str) -> tuple[str, str] | None:
    """Compatibility wrapper returning the deterministic Playground reply."""
    intent = classify_conversational_intent(question)
    return (intent.playground_reply, intent.name) if intent else None


def widget_conversational_reply(message: str) -> tuple[str, str] | None:
    """Return a channel-appropriate social response for a storefront visitor."""
    intent = classify_conversational_intent(message)
    return (intent.widget_reply, intent.name) if intent else None
