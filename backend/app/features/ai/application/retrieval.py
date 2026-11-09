"""Small, deterministic query expansion for tenant knowledge retrieval."""

import re
import unicodedata


_CONTEXT_REFERENCE_WORDS = frozenset(
    {
        "it", "that", "this", "they", "them", "those", "one", "same", "another",
        "also", "ani", "tesko", "tyo", "yo", "tiniharu", "tesma", "yesma",
        "त्यो", "यो", "तिनीहरू", "त्यसको", "यसको", "त्यसमा", "यसमा",
    }
)
_SHORT_CONTEXT_QUESTIONS = frozenset(
    {
        "why", "how", "when", "where", "which", "kina", "kasari", "kahile",
        "kaha", "kata", "kun", "kati", "किन", "कसरी", "कहिले", "कहाँ",
        "कुन", "कति",
    }
)
_CONTEXT_REFERENCE_PHRASES = re.compile(
    r"\b(?:what about|how about|how long|what if|and then|and this|and that|"
    r"tell me more|same for|what about this|yo pani|tesko barema|ani)\b",
    re.IGNORECASE,
)


def is_contextual_follow_up(text: str) -> bool:
    """Identify short references that need the preceding customer topic."""
    normalized = unicodedata.normalize("NFKC", text).casefold().strip()
    if _CONTEXT_REFERENCE_PHRASES.search(normalized):
        return True
    tokens = [
        token
        for token in re.findall(r"[\w\u0900-\u097f]+", normalized, flags=re.UNICODE)
        if token
    ]
    if len(tokens) <= 4 and any(token in _CONTEXT_REFERENCE_WORDS for token in tokens):
        return True
    return len(tokens) <= 2 and any(token in _SHORT_CONTEXT_QUESTIONS for token in tokens)

_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "can", "could", "do", "does",
        "for", "from", "have", "has", "how", "i", "in", "is", "it", "me", "my",
        "of", "on", "or", "our", "please", "the", "this", "to", "we", "what",
        "when", "where", "which", "who", "why", "with", "would", "you", "your",
        "kind", "type", "document", "documents", "information", "available",
        "के", "छ", "छन्", "हो", "म", "हाम्रो", "तपाईं", "तपाईँ", "तिम्रो",
        "कृपया", "मलाई", "र", "को", "का", "की", "मा", "ले", "लाई", "बाट",
        "यो", "त्यो", "कसरी", "कुन", "गर्न", "भन्ने",
        "mero", "hamro", "ko", "ka", "ki", "ma", "lai", "ra", "yo", "tyo",
        "kasari", "garna", "garnu", "garne", "cha", "chha", "ho", "kaha", "kata",
        "kahile", "pugyo",
    }
)

# Expand only well-defined support intents. These are retrieval hints, not claims
# about policy and not instructions to the model.
_INTENT_TERMS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        (
            "return", "returns", "refund", "refunds", "refunded", "exchange", "रिटर्न", "रिफन्ड",
            "फिर्ता", "phirta", "firta", "firtā", "return garna", "return kasari",
            "refund kasari", "paisa firta",
            "page says", "you said", "return window", "refund window", "how many days",
            "without receipt", "gift return", "final sale",
        ),
        ("return", "returns", "refund", "exchange", "policy", "eligible", "days", "window", "receipt"),
    ),
    (
        (
            "shipping", "ship", "shipped", "delivery", "deliver", "tracking", "track",
            "dispatch", "courier", "ढुवानी", "डेलिभरी", "पार्सल", "ट्र्याक", "order status",
            "mero order kaha", "mero order kata", "order kaha pugyo", "order kata pugyo",
            "parcel kaha", "parcel kata", "tracking kaha", "delivery kahile", "track garnu",
            "shipping fee", "shipping fees", "shipping cost", "shipping charge", "delivery fee",
            "delivery fees", "delivery charge", "delivery charges", "ढुवानी शुल्क", "डेलिभरी शुल्क",
            "delivery charge kati", "shipping kati",
            "how long does it take", "how long will it take", "how long does shipping take",
            "how long does delivery take", "delivery time", "shipping time",
            "when will it arrive", "when will my order arrive",
            "international shipping", "same day delivery",
        ),
        (
            "shipping", "shipment", "delivery", "dispatch", "tracking", "courier",
            "fee", "fees", "charge", "charges", "cost", "estimated delivery",
            "international", "same", "express",
        ),
    ),
    (
        (
            "cancel", "cancellation", "cancelled", "canceled", "रद्द", "cancel garna",
            "cancel garnu", "order cancel", "radd garna", "radd garnu",
        ),
        ("cancel", "cancellation", "order", "request"),
    ),
    (
        (
            "payment", "pay", "paid", "billing", "charged", "charge", "भुक्तानी", "तिर्न",
            "पैसा", "payment kasari", "pay garna", "paisa tirna",
            "esewa", "khalti", "digital wallet",
        ),
        ("payment", "billing", "pay", "charge", "card", "wallet", "method"),
    ),
    (
        (
            "warranty", "guarantee", "repair", "defect", "defective", "broken", "मर्मत",
            "वारेन्टी", "warranty cha", "repair garna", "saman bigryo",
        ),
        ("warranty", "guarantee", "repair", "defect", "damaged"),
    ),
    (
        (
            "store hours", "business hours", "opening hours", "working hours", "opening time",
            "when are you open", "when do you open", "when do you close", "खुल्ने समय",
            "खुल्ने टाइम", "खुल्छ", "खुल्नुहुन्छ", "kati baje khulcha", "kahile khulcha",
            "kati baje banda", "store kati baje",
        ),
        ("store", "business", "opening", "working", "hours", "time", "open", "close"),
    ),
    (
        (
            "contact", "contact information", "contact details", "phone number", "email address",
            "customer support", "support team", "सम्पर्क", "सम्पर्क नम्बर", "फोन नम्बर",
            "samparka", "phone number cha", "kasari contact", "support lai contact",
        ),
        ("contact", "support", "phone", "email", "address", "reach"),
    ),
    (
        (
            "payment method", "payment methods", "accepted payment", "accepted payments",
            "ways to pay", "pay with", "कुन माध्यमबाट भुक्तानी", "भुक्तानी विधि",
            "payment kasari garne", "kasari pay garne", "kun payment",
        ),
        ("payment", "payments", "method", "card", "cash", "bank", "wallet"),
    ),
    (
        (
            "in stock", "out of stock", "stock availability", "product availability",
            "available in stock", "स्टकमा", "स्टक छ", "उपलब्ध छ", "stock cha", "stock chha",
            "pauchha", "pauncha", "available cha", "available chha",
        ),
        ("stock", "inventory", "availability", "available", "quantity"),
    ),
    (
        (
            "product specification", "product specifications", "technical details", "product dimensions",
            "what is it made of", "size chart", "कस्तो सामग्री", "विशेषता", "विवरण",
            "आकार", "रङ", "rang", "size kati", "kun material", "specification ke ho",
        ),
        ("specification", "specifications", "features", "dimensions", "size", "color", "material"),
    ),
)


def build_retrieval_terms(text: str, *, limit: int = 64) -> list[str]:
    """Tokenize English, Devanagari, and Romanized Nepali text with bounded hints."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        # Letters, combining marks, and numbers stay together. This preserves
        # Nepali syllables while excluding punctuation that could alter tsquery.
        if unicodedata.category(character)[0] in {"L", "M", "N"}:
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    intent_tokens = tuple(tokens)
    tokens = [
        token
        for token in tokens
        if len(token) > 1 and token not in _STOPWORDS
    ]
    expanded = list(tokens)
    token_set = set(tokens)
    intent_token_set = set(intent_tokens)
    for triggers, synonyms in _INTENT_TERMS:
        if any(_matches_trigger(intent_token_set, intent_tokens, trigger) for trigger in triggers):
            expanded.extend(synonyms)
    return list(dict.fromkeys(expanded))[:limit]


def should_skip_semantic_retrieval(text: str) -> bool:
    """Skip query embedding for standalone greetings and thanks (keyword may still run)."""
    normalized = unicodedata.normalize("NFKC", text).casefold().strip()
    if not normalized:
        return True
    greeting = re.fullmatch(
        r"(?:hi|hello|hey|thanks|thank you|thx|namaste|नमस्ते|नमस्कार|धन्यवाद)(?: there| everyone| so much| a lot)?[!. ,]*",
        normalized,
    )
    if greeting:
        return True
    if len(normalized) <= 48 and is_contextual_follow_up(text) and not build_retrieval_terms(text):
        return True
    return False


def _matches_trigger(token_set: set[str], tokens: tuple[str, ...], trigger: str) -> bool:
    """Match whole words or contiguous phrases, never arbitrary substrings."""
    phrase = tuple(trigger.split())
    if len(phrase) == 1:
        return phrase[0] in token_set
    width = len(phrase)
    return any(tokens[index : index + width] == phrase for index in range(len(tokens) - width + 1))
