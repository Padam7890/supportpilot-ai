from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.routes.widgets import widget_message_out
from app.schemas.widget import WidgetMessageCreate


def message_with_metadata(metadata: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), sender_type="assistant", content="Phone options", created_at=datetime.now(UTC),
        provider_metadata=metadata,
    )


def test_widget_message_returns_only_validated_recommendation_contract():
    output = widget_message_out(message_with_metadata({
        "recommendation": {
            "schema_version": "1.0",
            "response_type": "recommendations",
            "explanation": "These fit the catalog criteria.",
            "products": [],
            "limitations": [],
            "available_actions": ["view_product"],
            "suggested_follow_ups": [],
            "provider_token": "must-not-leak",
        },
        "access_token": "must-not-leak",
    }))
    response = output.model_dump(mode="json")
    assert response["recommendation"]["explanation"] == "These fit the catalog criteria."
    assert "provider_token" not in response["recommendation"]
    assert "access_token" not in response


def test_widget_message_hides_invalid_structured_recommendation_payload():
    output = widget_message_out(message_with_metadata({"recommendation": {"sql": "select * from products"}}))
    assert output.recommendation is None


def test_widget_message_accepts_typed_comparison_result():
    output = widget_message_out(message_with_metadata({
        "recommendation": {
            "schema_version": "1.0",
            "response_type": "comparison",
            "explanation": "Verified differences.",
            "products": [],
            "differences": ["Price differs"],
        },
    }))
    assert output.recommendation is not None
    assert output.recommendation.response_type == "comparison"


def test_widget_comparison_selection_contract_allows_up_to_four_items():
    selections = [{"product_id": str(uuid4()), "variant_id": str(uuid4())} for _ in range(4)]
    payload = WidgetMessageCreate(content="Compare these", recommendation_selections=selections)
    assert len(payload.recommendation_selections or []) == 4
    with pytest.raises(ValueError):
        WidgetMessageCreate(content="Compare these", recommendation_selections=selections + selections[:1])
