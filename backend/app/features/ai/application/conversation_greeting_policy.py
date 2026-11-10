"""Conservative response policy for the default first-contact agent pilot.

This is an output safety boundary, not a substitute for semantic grounding.
"""

import re

_STORE_ASSERTION = re.compile(
    r"\b(?:in stock|out of stock|available products?|"
    r"shipping (?:takes|costs|is)|delivery (?:takes|costs|is)|"
    r"refunds? (?:are|is|take|takes)|returns? (?:are|is|take|takes)|"
    r"your order|order status|we (?:offer|sell|have|ship|refund)|"
    r"discount|price|guaranteed|warranty)\b",
    re.IGNORECASE,
)


def safe_first_contact_greeting(answer: str) -> bool:
    """Permit short greetings without unverifiable merchant-specific claims."""
    normalized = answer.strip()
    return bool(
        normalized
        and len(normalized) <= 300
        and not re.search(r"\d", normalized)
        and not _STORE_ASSERTION.search(normalized)
        and not re.search(r"https?://|@|\$", normalized)
    )
