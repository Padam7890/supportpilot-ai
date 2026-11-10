"""Order snapshots retain approved facts and discard private provider fields."""

from app.features.ai.application.conversation_verified_order_evidence import AuthorizedOrderSnapshot


def test_snapshot_excludes_private_fields_and_bounds_tracking():
    snapshot = AuthorizedOrderSnapshot.model_validate({
        "order_number": "#1234",
        "financial_status": "PAID",
        "fulfillment_status": "FULFILLED",
        "return_status": "NO_RETURN",
        "total_amount": "125.00",
        "currency": "USD",
        "email": "customer@example.com",
        "shipping_address": {"address1": "private street"},
        "access_token": "secret",
        "tracking": [
            {"company": "Carrier", "number": "ABC123", "url": "https://private.example/track"},
            {},
            {},
            {"number": "outside-limit"},
        ],
    })
    evidence = snapshot.as_evidence()
    assert evidence.status == "verified"
    content = evidence.items[0].content
    assert "#1234" in content
    assert "125.00 USD" in content
    assert "ABC123" in content
    assert "Carrier" in content
    assert "private" not in content
    assert "outside-limit" not in content
    assert "secret" not in snapshot.model_dump_json()
    assert "customer@example.com" not in snapshot.model_dump_json()
