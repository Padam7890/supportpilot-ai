"""Regression tests for at-most-once Shopify cancellation dispatch."""
import pytest

from app.services.commerce_action_recovery import decide_lease_recovery


@pytest.mark.parametrize("attempts", [1, 2, 3, 99])
def test_shopify_expired_running_lease_never_retries(attempts: int) -> None:
    assert decide_lease_recovery(
        provider="shopify", status="running", lease_expired=True,
        attempts=attempts, max_attempts=3,
    ) == "manual_reconciliation"


def test_newly_approved_shopify_action_can_dispatch_once() -> None:
    assert decide_lease_recovery(
        provider="shopify", status="queued", lease_expired=False,
        attempts=0, max_attempts=3,
    ) == "dispatch"


def test_mock_action_can_retry_after_expired_lease() -> None:
    assert decide_lease_recovery(
        provider="mock", status="running", lease_expired=True,
        attempts=1, max_attempts=3,
    ) == "dispatch"


def test_mock_exhausted_action_stops() -> None:
    assert decide_lease_recovery(
        provider="mock", status="running", lease_expired=True,
        attempts=3, max_attempts=3,
    ) == "retry_limit"


def test_active_lease_is_never_reclaimed() -> None:
    with pytest.raises(ValueError, match="Active lease"):
        decide_lease_recovery(
            provider="shopify", status="running", lease_expired=False,
            attempts=1, max_attempts=3,
        )


def test_unknown_provider_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        decide_lease_recovery(
            provider="unknown", status="queued", lease_expired=False,
            attempts=0, max_attempts=3,
        )
