"""Regression: customer API response models must accept DB-stored synthetic emails."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.customer import CustomerOut


def test_customer_out_accepts_synthetic_placeholder_email_domains():
    now = datetime.now(UTC)
    row = CustomerOut(
        id=uuid4(),
        organization_id=uuid4(),
        name="Store visitor",
        email="visitor+abc123@widget.invalid",
        phone=None,
        external_reference=None,
        created_at=now,
        updated_at=now,
    )
    assert row.email == "visitor+abc123@widget.invalid"
