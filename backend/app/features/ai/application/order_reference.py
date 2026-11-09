"""Recognize order reference availability without interpreting it as authorization."""

import re

_ORDER_NUMBER = r"order\s+(?:number|reference|id|no\.?)"
_UNAVAILABLE = (
    r"forg(?:et|ot(?:ten)?)|lost|misplaced|don.t (?:know|remember|have)|"
    r"do not (?:know|remember|have)|can(?:not|.t) (?:find|remember|locate)|"
    r"could(?: not|n.t) (?:find|remember|locate)"
)
_EXPLICIT_MISSING = re.compile(
    rf"\b(?:{_UNAVAILABLE})\s+(?:(?:what|where to find)\s+)?(?:(?:the|my|an|any)\s+)?{_ORDER_NUMBER}\b|"
    rf"\bno\s+{_ORDER_NUMBER}\b|\b{_ORDER_NUMBER}\s+is\s+(?:missing|lost)\b",
    re.IGNORECASE,
)
_CONTEXTUAL_MISSING = re.compile(
    rf"(?:sorry[,. ]+)?(?:i\s+)?(?:{_UNAVAILABLE})"
    r"\s+(?:(?:the|my|it.s)\s+)?(?:number|reference|it|that)[.! ]*",
    re.IGNORECASE,
)
_REFERENCE_PROVIDED = re.compile(
    rf"\b{_ORDER_NUMBER}\s*(?:is\s+|[:=]\s*)?#?[\w-]*\d[\w-]*\b|"
    r"(?:^|\s)#[\w-]*\d[\w-]*\b|"
    r"^(?:(?:actually|yes)[, ]+)?i (?:found|have|remember) (?:it|the (?:order )?number)[.! ]*$",
    re.IGNORECASE,
)


def order_reference_unavailable(message: str, *, in_order_context: bool = False) -> bool:
    return bool(
        _EXPLICIT_MISSING.search(message)
        or (in_order_context and _CONTEXTUAL_MISSING.fullmatch(message.strip()))
    )


def order_reference_recovered(message: str) -> bool:
    return bool(_REFERENCE_PROVIDED.search(message))
