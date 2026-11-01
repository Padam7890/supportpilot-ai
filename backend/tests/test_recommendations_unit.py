from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.recommendations import (
    ComparedProduct,
    RecommendationExecutionOut,
    RecommendationIntent,
)
from app.services.product_comparison import compare_verified_products
from app.services.recommendations import (
    CatalogCandidate,
    build_recommendation_result,
    parse_intent_output,
)


def candidate(*, title: str, price: str, currency: str = "NPR", brand: str = "Acme", category: str = "Phones", availability: str = "available", features: dict[str, str] | None = None) -> CatalogCandidate:
    now = datetime.now(UTC)
    product = SimpleNamespace(
        id=uuid4(), title=title, description="A phone with camera and battery details", brand=brand,
        category=category, specifications={}, images=[], canonical_url=None, updated_at=now,
    )
    variant = SimpleNamespace(
        id=uuid4(), title="Standard", attributes=features or {}, price=Decimal(price), currency=currency,
        availability=availability,
    )
    return CatalogCandidate(product=product, variant=variant)


@pytest.mark.parametrize(
    ("message", "expected_category", "expected_currency"),
    [
        ("Recommend a smartphone under Rs. 30,000 with good camera and battery", "smartphone", None),
        ("मोबाइल सिफारिस गर्नुहोस् रु ३००००", "मोबाइल", "NPR"),
        ("Mobile suggest gara budget NPR 30000", "mobile", "NPR"),
    ],
)
def test_malformed_intent_uses_bounded_multilingual_fallback(message, expected_category, expected_currency):
    result = parse_intent_output("not valid json", message)
    assert result.is_recommendation
    assert result.category == expected_category
    assert result.budget_currency == expected_currency


@pytest.mark.parametrize("raw", ["{}", "[]", '{"budget_amount":"-10"}', '{"result_count":100}'])
def test_invalid_or_incomplete_model_output_falls_back_safely(raw):
    result = parse_intent_output(raw, "Recommend a phone under NPR 25000")
    assert result.is_recommendation is True
    assert result.budget_amount == Decimal(25000)
    assert result.result_count == 3


def test_model_extraction_schema_rejects_extra_fields():
    with pytest.raises(ValueError):
        RecommendationIntent.model_validate({"is_recommendation": True, "sql": "select * from catalog"})


def test_strict_budget_boundary_is_inclusive_and_never_exceeded():
    at_limit = candidate(title="Budget phone camera", price="30000")
    over_limit = candidate(title="Premium phone camera", price="30000.01")
    intent = RecommendationIntent(category="phone", budget_amount=Decimal(30000), budget_currency="NPR", budget_strict=True, required_features=["camera"])
    result = build_recommendation_result("phone under NPR 30000", intent, [at_limit, over_limit])
    assert result.response_type == "recommendations"
    assert [item.product_id for item in result.products] == [at_limit.product.id]


def test_flexible_budget_discloses_bounded_overage():
    candidate_at_limit = candidate(title="Budget phone", price="30000")
    candidate_over = candidate(title="Flexible phone", price="33000")
    candidate_too_high = candidate(title="Expensive phone", price="36000.01")
    intent = RecommendationIntent(category="phone", budget_amount=Decimal(30000), budget_currency="NPR", budget_strict=False)
    result = build_recommendation_result("phone around NPR 30000", intent, [candidate_at_limit, candidate_over, candidate_too_high])
    assert {item.product_id for item in result.products} == {candidate_at_limit.product.id, candidate_over.product.id}
    overage = next(item for item in result.products if item.product_id == candidate_over.product.id)
    assert overage.budget_overage == Decimal(3000)
    assert any("above your flexible budget" in limitation for limitation in overage.limitations)


def test_currency_is_never_converted_and_ambiguous_currency_requests_clarification():
    npr = candidate(title="Phone camera", price="25000", currency="NPR")
    usd = candidate(title="Other phone camera", price="100", currency="USD")
    intent = RecommendationIntent(category="phone", budget_amount=Decimal(30000), budget_strict=True)
    result = build_recommendation_result("Phone under Rs 30000", intent, [npr, usd])
    assert result.response_type == "clarification"
    assert not result.products


def test_unknown_currency_is_inferred_only_when_catalog_has_one_currency():
    npr = candidate(title="Phone camera", price="25000", currency="NPR")
    intent = RecommendationIntent(category="phone", budget_amount=Decimal(30000), budget_strict=True)
    result = build_recommendation_result("Phone under 30000", intent, [npr])
    assert result.response_type == "recommendations"
    assert result.applied_criteria.budget_currency == "NPR"


def test_excluded_brands_and_unavailable_variants_are_not_recommended():
    excluded = candidate(title="Phone camera", price="20000", brand="Acme")
    intent = RecommendationIntent(category="phone", excluded_brands=["Acme"])
    result = build_recommendation_result("Recommend phone", intent, [excluded])
    assert result.response_type == "no_match"
    unavailable = candidate(title="Phone camera", price="20000", availability="unavailable")
    assert not build_recommendation_result("Recommend phone", RecommendationIntent(category="phone"), [unavailable]).products


def test_recommendations_deduplicate_variants_and_ground_tradeoffs_in_catalog():
    variant_one = candidate(title="Phone camera", price="24000")
    variant_two = CatalogCandidate(product=variant_one.product, variant=candidate(title="ignored", price="25000").variant)
    result = build_recommendation_result("Recommend phone camera", RecommendationIntent(category="phone", required_features=["camera"]), [variant_one, variant_two])
    assert len(result.products) == 1
    assert {item.variant_id for item in result.products[0].variant_options} == {
        variant_one.variant.id,
        variant_two.variant.id,
    }
    assert "camera" in " ".join(result.products[0].reasons).lower()
    assert "Structured product specifications are not available" in result.products[0].limitations


def test_close_scoring_results_diversify_across_brands_when_not_requested():
    first_brand = candidate(title="Phone camera", price="24000", brand="Brand A")
    second_brand = candidate(title="Phone camera", price="24100", brand="Brand B")
    result = build_recommendation_result(
        "Recommend a phone with camera",
        RecommendationIntent(category="phone", required_features=["camera"], result_count=2),
        [first_brand, second_brand],
    )
    assert len(result.products) == 2
    assert {item.brand for item in result.products} == {"Brand A", "Brand B"}


def test_non_recommendation_is_typed_unsupported_response():
    result = build_recommendation_result("Where is my order?", RecommendationIntent(is_recommendation=False), [])
    assert result.response_type == "unsupported"
    assert not result.products


@pytest.mark.parametrize(
    ("intent", "response_type"),
    [
        (RecommendationIntent(category="spaceship"), "clarification"),
        (RecommendationIntent(category="phone", required_features=["waterproof"]), "no_match"),
    ],
)
def test_unknown_category_and_unverified_required_features_do_not_invent_results(intent, response_type):
    phone = candidate(title="Phone with camera", price="25000")
    result = build_recommendation_result("Recommend a product", intent, [phone])
    assert result.response_type == response_type
    assert not result.products


def test_empty_catalog_returns_typed_no_match():
    result = build_recommendation_result("Recommend a phone", RecommendationIntent(category="phone"), [])
    assert result.response_type == "no_match"
    assert not result.products


def test_recommendation_execution_response_serializes_the_typed_result_only():
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id=uuid4(), kind="recommendation", status="succeeded", recommendation_result={
            "schema_version": "1.0", "response_type": "clarification", "explanation": "Which currency?",
            "applied_criteria": None, "products": [], "limitations": [], "available_actions": ["refine_search"],
            "suggested_follow_ups": [],
        }, safe_summary="Completed", error_code=None, created_at=now, updated_at=now,
        started_at=now, completed_at=now, question="private prompt", instructions="private", usage={"total_tokens": 3},
    )
    payload = RecommendationExecutionOut.model_validate(row).model_dump()
    assert payload["result"]["response_type"] == "clarification"
    assert "question" not in payload
    assert "usage" not in payload


def test_comparison_normalizes_units_and_explains_priority_tradeoffs_with_missing_data():
    first = ComparedProduct(
        product_id=uuid4(), variant_id=uuid4(), title="Phone A", brand="A", category="phone",
        price=Decimal(25000), currency="NPR", availability="available",
        verified_attributes={"Battery": "5000 mAh", "Weight": "0.2 kg"},
    )
    second = ComparedProduct(
        product_id=uuid4(), variant_id=uuid4(), title="Phone B", brand="B", category="phone",
        price=Decimal(28000), currency="NPR", availability="available",
        verified_attributes={"battery": "5 Ah", "Weight": "200 g", "Camera": "50 MP"},
    )
    third = ComparedProduct(
        product_id=uuid4(), variant_id=uuid4(), title="Phone C", brand="C", category="phone",
        price=Decimal(30000), currency="NPR", availability="unknown",
        verified_attributes={"Camera": "12 MP"},
    )
    result = compare_verified_products([first, second, third], priorities=["battery", "camera"])
    assert result.response_type == "comparison"
    assert len(result.products) == 3
    assert result.products[0].normalized_attributes["Weight"] == "200 g (catalog: 0.2 kg)"
    assert any("Not listed" in difference for difference in result.differences)
    assert any("battery priority" in tradeoff and "5,000 mAh" in tradeoff for tradeoff in result.trade_offs)
    assert any("camera priority" in tradeoff and "not listed" in tradeoff for tradeoff in result.trade_offs)


def test_comparison_schema_caps_product_count_at_four():
    products = [
        ComparedProduct(
            product_id=uuid4(), variant_id=uuid4(), title=f"Phone {index}", brand=None, category="phone",
            price=Decimal(1), currency="NPR", availability="unknown", verified_attributes={},
        )
        for index in range(5)
    ]
    result = compare_verified_products(products[:4])
    assert len(result.products) == 4
    with pytest.raises(ValueError):
        type(result)(response_type="comparison", explanation="test", products=products)
