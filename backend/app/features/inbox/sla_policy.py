"""Shared SQL policy for workspace first-response targets."""

from sqlalchemy import Integer, case, cast, func


DEFAULT_FIRST_RESPONSE_SLA_MINUTES = {
    "low": 1440,
    "normal": 480,
    "high": 120,
    "urgent": 30,
}


def sla_target_minutes_expression(raw_sla, priority):
    """Resolve a validated workspace target, falling back to priority defaults."""
    raw_minutes = raw_sla[priority].as_string()
    parsed_minutes = case(
        (
            (func.jsonb_typeof(raw_sla[priority]) == "number")
            & raw_minutes.op("~")(r"^[0-9]{1,5}$"),
            cast(raw_minutes, Integer),
        ),
        else_=None,
    )
    return case(
        (parsed_minutes.between(5, 10080), parsed_minutes),
        else_=case(DEFAULT_FIRST_RESPONSE_SLA_MINUTES, value=priority),
    )
