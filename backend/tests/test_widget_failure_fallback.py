"""Failure fallback selection is safe and deterministic."""

from app.features.ai.application.widget_failure_fallback import plan_widget_failure_fallback


def test_provider_failure_with_retrieval_uses_provider_unavailable_reply() -> None:
    result = plan_widget_failure_fallback(
        failure_stage="provider_configuration",
        provider_failed=True,
        retrieval_match_count=2,
        provider_unavailable_reply="Provider unavailable",
        temporary_failure_reply="Please try again",
    )
    assert result.draft == "Provider unavailable"
    assert result.retain_retrieval_evidence is True


def test_retrieval_failure_uses_generic_handoff_without_evidence() -> None:
    result = plan_widget_failure_fallback(
        failure_stage="knowledge_retrieval",
        provider_failed=False,
        retrieval_match_count=None,
        provider_unavailable_reply="Provider unavailable",
        temporary_failure_reply="Please try again",
    )
    assert result.draft == "Please try again"
    assert result.retain_retrieval_evidence is False
    assert "handoff" in result.safe_summary


def test_provider_failure_without_sources_uses_generic_handoff() -> None:
    result = plan_widget_failure_fallback(
        failure_stage="provider_generation",
        provider_failed=True,
        retrieval_match_count=0,
        provider_unavailable_reply="Provider unavailable",
        temporary_failure_reply="Please try again",
    )
    assert result.draft == "Please try again"
