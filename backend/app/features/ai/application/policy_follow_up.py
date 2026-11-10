"""Typed policy follow-up context carried by the existing assistant message state."""

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# A fast-path hint for the date slot. Other question and follow-up wording
# is interpreted by the shared structured intent router.
_DELIVERY_DATE = re.compile(r"\bdelivery date\b", re.IGNORECASE)
_ABSOLUTE_DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|"
    r"\d{1,2} [a-z]{3,9} \d{4}|[a-z]{3,9} \d{1,2},? \d{4})\b", re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
_RELATIVE_DATE = re.compile(
    r"last (" + "|".join(calendar.day_name) + r")|today|yesterday", re.IGNORECASE,
)

_SMALL_NUMBERS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


class DeliveryDate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original: str = Field(max_length=40)
    normalized: date


class PolicyConversation(BaseModel):
    """Customer-supplied context. It carries no policy or order authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    topic: str = Field(min_length=1, max_length=240)
    assistant_question: str = Field(min_length=1, max_length=240)
    delivery_date: DeliveryDate | None = None
    quantity: int | None = Field(default=None, ge=1, le=1000)
    source_document_ids: tuple[UUID, ...] = Field(default=(), max_length=6)


class FollowUpInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    relation: Literal["new_topic", "follow_up", "answer_to_question", "unclear"]
    goal: Literal["delivery_date", "replacement", "refund", "next_step", "policy_question", "none"]
    date_text: str | None = Field(default=None, max_length=40)
    quantity_text: str | None = Field(default=None, max_length=40)
    confidence: float = Field(ge=0, le=1)


@dataclass(frozen=True)
class PolicyFollowUp:
    kind: Literal["delivery_date", "ambiguous_date", "replacement", "refund", "next_step", "policy_question"]
    query: str
    state: PolicyConversation


def asks_delivery_date(text: str) -> bool:
    return "?" in text[-400:] and bool(_DELIVERY_DATE.search(text[-400:]))


def parse_policy_quantity(text: str) -> int | None:
    text = text.casefold()
    if text.isdecimal():
        return int(text) if len(text) <= 4 else None
    words = text.replace("-", " ").split()
    if text in _SMALL_NUMBERS:
        return _SMALL_NUMBERS.index(text)
    if words and words[0] in _TENS and (
        len(words) == 1 or (len(words) == 2 and words[1] in _SMALL_NUMBERS[1:10])
    ):
        return (_TENS.index(words[0]) + 2) * 10 + (
            _SMALL_NUMBERS.index(words[1]) if len(words) == 2 else 0
        )
    return None


def _relative_date(value: str, today: date) -> date:
    if value == "today":
        return today
    if value == "yesterday":
        return today - timedelta(days=1)
    weekday = list(calendar.day_name).index(value.removeprefix("last ").title())
    return today - timedelta(days=(today.weekday() - weekday) % 7 or 7)


def normalize_delivery_date(value: str, now: datetime) -> DeliveryDate | None:
    folded = value.casefold()
    if _RELATIVE_DATE.fullmatch(folded):
        earliest = (now.astimezone(UTC) - timedelta(hours=12)).date()
        latest = (now.astimezone(UTC) + timedelta(hours=14)).date()
        # Without a store zone, accept relative dates only if every possible
        # local reference date resolves to the same date.
        candidates = {
            _relative_date(folded, earliest), _relative_date(folded, latest)
        }
        if len(candidates) == 1:
            return DeliveryDate(original=value, normalized=candidates.pop())
        return None
    if not _ABSOLUTE_DATE.fullmatch(value):
        return None
    try:
        if parts := _NUMERIC_DATE.fullmatch(value):
            first, second, year = map(int, parts.groups())
            if max(first, second) <= 12:
                return None
            month, day = sorted((first, second))
            return DeliveryDate(original=value, normalized=date(year, month, day))
        for layout in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
            try:
                return DeliveryDate(
                    original=value,
                    normalized=datetime.strptime(value.replace(",", ""), layout).date(),
                )
            except ValueError:
                continue
    except ValueError:
        return None
    return None


def resolve_policy_follow_up(
    message: str,
    state: PolicyConversation,
    now: datetime,
    *,
    interpretation: FollowUpInterpretation | None = None,
) -> PolicyFollowUp | None:
    if interpretation is None:
        # Only a standalone date plus conversational date words can use the
        # fast path. A compound request goes to semantic understanding.
        found = list(_ABSOLUTE_DATE.finditer(message))
        if len(found) != 1 or not asks_delivery_date(state.assistant_question):
            return None
        candidate = found[0]
        surrounding = message[:candidate.start()] + message[candidate.end():]
        date_words = {"the", "my", "date", "delivery", "is", "was", "on", "it", "arrived",
                      "delivered", "sorry", "actually", "received", "came"}
        if set(re.findall(r"\w+", surrounding.casefold())) - date_words:
            return None
        goal, value = "delivery_date", candidate[0]
    else:
        if interpretation.relation not in {"follow_up", "answer_to_question"}:
            return None
        goal, value = interpretation.goal, interpretation.date_text
        quantity = interpretation.quantity_text
        if quantity and re.search(rf"(?<!\w){re.escape(quantity)}(?!\w)", message, re.IGNORECASE):
            amount = parse_policy_quantity(quantity)
            if amount and amount <= 1000:
                state = state.model_copy(update={"quantity": amount})
    if goal == "delivery_date":
        if interpretation is not None and interpretation.relation != "answer_to_question":
            return None
        if len(_ABSOLUTE_DATE.findall(message)) > 1:
            value = None
        # A model may select a span. It cannot create or normalize the date.
        delivery = normalize_delivery_date(value, now) if value and value.casefold() in message.casefold() else None
        return PolicyFollowUp(
            "delivery_date" if delivery else "ambiguous_date",
            f"{state.topic} reporting deadline from delivery",
            state.model_copy(update={"delivery_date": delivery}),
        )
    if goal == "none":
        return None
    topic = {
        "replacement": "replacement exchange policy",
        "refund": "refund return policy",
        "next_step": "policy procedure next steps",
        "policy_question": "store policy",
    }[goal]
    return PolicyFollowUp(goal, f"{state.topic} {topic}", state)
