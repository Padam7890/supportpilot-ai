"""Deterministic fallback selection for failed storefront AI replies.

No exception messages or private customer data enter the reply.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WidgetFailureFallback:
    draft: str
    safe_summary: str
    retain_retrieval_evidence: bool


def plan_widget_failure_fallback(
    *,
    failure_stage: str,
    provider_failed: bool,
    retrieval_match_count: int | None,
    provider_unavailable_reply: str,
    temporary_failure_reply: str,
) -> WidgetFailureFallback:
    draft = (
        provider_unavailable_reply
        if provider_failed and retrieval_match_count
        else temporary_failure_reply
    )
    summary = {
        "provider_configuration": "Chat provider configuration prevented generation.",
        "provider_generation": "AI generation could not complete.",
        "knowledge_retrieval": "Knowledge retrieval could not complete.",
        "reply_persistence": "The generated reply could not be saved.",
    }.get(failure_stage, "AI reply processing could not complete.")
    return WidgetFailureFallback(
        draft=draft,
        safe_summary=summary + " A safe handoff reply was prepared.",
        retain_retrieval_evidence=failure_stage == "provider_configuration",
    )
