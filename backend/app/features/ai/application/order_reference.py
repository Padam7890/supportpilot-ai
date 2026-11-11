"""Deterministic parsing of an order reference supplied by a customer.

Whether a customer cannot find a reference is a conversational interpretation and
is resolved by the shared intent router. This module only validates that a
message contains a reference-shaped value before the secure verification flow.
"""

import re

_REFERENCE_PROVIDED = re.compile(
    r"\border\s+(?:number|reference|id|no\.?)\s*(?:is\s+|[:=]\s*)?#?[\w-]*\d[\w-]*\b|"
    r"(?:^|\s)#[\w-]*\d[\w-]*\b",
    re.IGNORECASE,
)


def order_reference_recovered(message: str) -> bool:
    """Return true only when a customer supplied a parseable reference token."""
    return bool(_REFERENCE_PROVIDED.search(message))
