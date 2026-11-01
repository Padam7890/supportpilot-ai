from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.conversation import ConversationOut
from app.schemas.recommendations import RecommendationIntent
from app.services.recommendation_conversation import (
    SHOPPING_CUES,
    ShoppingConversationState,
    ShoppingTurnAnalysis,
    apply_shopping_turn,
    fallback_turn_analysis,
    invoke_recommend_products,
    load_shopping_state,
    process_widget_shopping_turn,
    shopping_state_is_expired,
)
from app.services.recommendation_tool_registry import (
    CompareProductsInput,
    ToolReference,
    validate_tool_input,
)
from app.services.recommendations import CatalogCandidate, build_recommendation_result


def state_with_results(count: int = 2) -> ShoppingConversationState:
    state = ShoppingConversationState(
        active=True,
        intent=RecommendationIntent(
            category="phone", budget_amount="30000", budget_currency="NPR", budget_strict=True
        ),
        required_constraints=["5g"],
        soft_preferences={"battery": 2},
    )
    state.last_displayed_recommendations = [ToolReference(product_id=uuid4(), variant_id=uuid4()) for _ in range(count)]
    return state


def test_brand_only_turn_preserves_category_budget_and_hard_constraints():
    state = state_with_results()
    analysis = fallback_turn_analysis("Samsung only", state, brands=["Samsung"])
    assert analysis.action == "change_brand"
    next_state, action, _, _ = apply_shopping_turn(state, analysis)
    assert action == "recommend"
    assert next_state.intent.category == "phone"
    assert next_state.intent.budget_amount == 30000
    assert next_state.intent.required_brand == "Samsung"
    assert next_state.required_constraints == ["5g"]


def test_better_camera_is_soft_preference_and_increases_weight():
    state = state_with_results()
    analysis = fallback_turn_analysis("Better camera", state)
    next_state, action, _, _ = apply_shopping_turn(state, analysis)
    assert action == "recommend"
    assert next_state.soft_preferences["camera"] == 2
    assert "camera" not in next_state.required_constraints
    assert next_state.intent.category == "phone"
    assert next_state.intent.budget_amount == 30000


def test_cheaper_followup_sorts_by_price_without_relaxing_strict_budget():
    state = state_with_results()
    analysis = fallback_turn_analysis("Show cheaper options", state)
    next_state, action, _, _ = apply_shopping_turn(state, analysis)
    assert action == "recommend"
    assert next_state.intent.sort_by == "price_asc"
    assert next_state.intent.budget_amount == Decimal(30000)
    assert next_state.intent.budget_strict is True


def test_soft_preference_weight_changes_ranking_deterministically():
    now = datetime.now(UTC)

    def item(title: str, attributes: dict[str, str]) -> CatalogCandidate:
        product = SimpleNamespace(
            id=uuid4(), title=title, description="", brand="Acme", category="phone",
            specifications={}, images=[], canonical_url=None, updated_at=now,
        )
        variant = SimpleNamespace(
            id=uuid4(), title="Base", attributes=attributes, price=Decimal(100),
            currency="NPR", availability="available",
        )
        return CatalogCandidate(product, variant)

    camera = item("Phone camera", {"camera": "good"})
    battery = item("Phone battery", {"battery": "long"})
    intent = RecommendationIntent(category="phone", optional_preferences=["camera", "battery"], result_count=2)
    result = build_recommendation_result(
        "phone", intent, [camera, battery], soft_preference_weights={"camera": 5, "battery": 1}
    )
    assert result.products[0].product_id == camera.product.id


def test_replacing_budget_category_and_brand_does_not_clear_other_slots():
    state = state_with_results()
    state, _, _, _ = apply_shopping_turn(
        state,
        ShoppingTurnAnalysis(
            action="change_budget",
            intent_patch=RecommendationIntent(budget_amount=Decimal(45000), budget_currency="NPR"),
        ),
    )
    assert state.intent.category == "phone"
    assert state.intent.budget_amount == 45000
    state, _, _, _ = apply_shopping_turn(
        state,
        ShoppingTurnAnalysis(action="change_category", intent_patch=RecommendationIntent(category="laptop")),
    )
    assert state.intent.category == "laptop"
    assert state.intent.budget_amount == 45000


def test_add_remove_preference_and_reset_clear_context():
    state = state_with_results()
    state, _, _, _ = apply_shopping_turn(
        state, ShoppingTurnAnalysis(action="add_preference", preference="camera", preference_delta=2)
    )
    assert state.soft_preferences["camera"] == 3
    state, _, _, _ = apply_shopping_turn(
        state, ShoppingTurnAnalysis(action="remove_preference", preference="battery")
    )
    assert "battery" not in state.soft_preferences
    cleared, action, _, reply = apply_shopping_turn(state, ShoppingTurnAnalysis(action="reset"))
    assert action == "reset"
    assert not cleared.active and not cleared.rejected_product_ids and not cleared.last_displayed_recommendations
    assert reply


def test_reject_reference_excludes_product_and_offers_handoff_only_after_three_turns():
    state = state_with_results()
    rejected_id = state.last_displayed_recommendations[0].product_id
    for attempt in range(2):
        analysis = fallback_turn_analysis("I don't like the first one", state)
        state, action, _, _ = apply_shopping_turn(state, analysis)
        assert action == "recommend"
        assert state.handoff_offer_pending is False
    analysis = fallback_turn_analysis("skip the first one", state)
    state, action, _, text = apply_shopping_turn(state, analysis)
    assert action == "handoff_offer"
    assert text and state.handoff_offer_pending
    assert rejected_id in state.rejected_product_ids
    state, action, _, _ = apply_shopping_turn(state, ShoppingTurnAnalysis(action="accept_handoff"))
    assert action == "handoff"
    assert not state.handoff_offer_pending


def test_ambiguous_comparison_asks_and_followup_first_two_resolves():
    state = state_with_results()
    state, action, refs, _ = apply_shopping_turn(state, ShoppingTurnAnalysis(action="compare"))
    assert action == "clarify" and refs == []
    assert state.clarification_state == "comparison_reference"
    analysis = fallback_turn_analysis("the first two", state)
    state, action, refs, _ = apply_shopping_turn(state, analysis)
    assert action == "compare"
    assert refs == state.last_displayed_recommendations
    assert state.selected_products_for_comparison == refs


def test_compare_positions_support_two_through_four_products():
    state = state_with_results(4)
    analysis = fallback_turn_analysis("Compare the first three", state)
    assert analysis.action == "compare"
    state, action, refs, _ = apply_shopping_turn(state, analysis)
    assert action == "compare"
    assert len(refs) == 3
    assert state.selected_products_for_comparison == refs


def test_alternatives_exclude_rejected_products_without_relaxing_hard_constraints():
    state = state_with_results(4)
    prior_intent = state.intent.model_copy(deep=True)
    first_id = state.last_displayed_recommendations[0].product_id
    analysis = fallback_turn_analysis("Find an alternative to the first one", state)
    assert analysis.action == "find_alternatives"
    state, action, _, _ = apply_shopping_turn(state, analysis)
    assert action == "recommend"
    assert first_id in state.rejected_product_ids
    assert state.rejected_product_ids == [first_id]
    assert state.intent == prior_intent


def test_alternative_request_can_apply_an_explicit_new_budget_but_keeps_it_strict():
    state = state_with_results()
    analysis = fallback_turn_analysis("another phone under NPR 25000", state)
    assert analysis.action == "find_alternatives"
    state, action, _, _ = apply_shopping_turn(state, analysis)
    assert action == "recommend"
    assert state.intent.budget_amount == Decimal(25000)
    assert state.intent.budget_currency == "NPR"
    assert state.intent.budget_strict is True


@pytest.mark.anyio
async def test_alternative_search_omits_rejected_products_and_keeps_strict_budget(monkeypatch):
    now = datetime.now(UTC)

    def item(title: str, price: str) -> CatalogCandidate:
        product = SimpleNamespace(
            id=uuid4(), title=title, description="", brand="Acme", category="phone",
            specifications={}, images=[], canonical_url="https://store.example/product", updated_at=now,
        )
        variant = SimpleNamespace(
            id=uuid4(), title="Standard", attributes={}, price=Decimal(price), currency="NPR",
            availability="available",
        )
        return CatalogCandidate(product, variant)

    rejected = item("Phone rejected", "20000")
    eligible = item("Phone alternative", "25000")

    async def fake_load_candidates(_db, _organization_id, _question):
        return [rejected, eligible], ["phone"], ["Acme"]

    monkeypatch.setattr("app.services.recommendation_conversation.load_candidates", fake_load_candidates)
    state = ShoppingConversationState(
        active=True,
        intent=RecommendationIntent(category="phone", budget_amount=Decimal(25000), budget_currency="NPR", budget_strict=True),
        rejected_product_ids=[rejected.product.id],
    )
    output, _refs = await invoke_recommend_products(None, uuid4(), "Show another phone", state)
    assert [product.product_id for product in output.result.products] == [eligible.product.id]
    assert all(product.price <= Decimal(25000) for product in output.result.products)


def test_generic_alternatives_skip_every_product_in_previous_result():
    state = state_with_results(3)
    prior_intent = state.intent.model_copy(deep=True)
    state, action, _, _ = apply_shopping_turn(state, ShoppingTurnAnalysis(action="find_alternatives"))
    assert action == "recommend"
    assert set(state.rejected_product_ids) == {item.product_id for item in state.last_displayed_recommendations}
    assert state.intent == prior_intent


def test_reject_without_reference_clarifies_and_single_option_followup_resolves():
    state = state_with_results()
    state, action, _, _ = apply_shopping_turn(state, ShoppingTurnAnalysis(action="reject"))
    assert action == "clarify"
    analysis = fallback_turn_analysis("the first one", state)
    state, action, _, _ = apply_shopping_turn(state, analysis)
    assert action == "recommend"
    assert state.rejected_product_ids == [state.last_displayed_recommendations[0].product_id]


def test_shopping_state_expires_and_malformed_persisted_state_fails_closed():
    now = datetime.now(UTC)
    assert shopping_state_is_expired(now - timedelta(days=30), now=now)
    state, expired = load_shopping_state({"not": "valid"}, now + timedelta(days=1), now=now)
    assert expired and not state.active
    state, expired = load_shopping_state({"active": True}, now + timedelta(days=1), now=now)
    assert not expired and state.active


def test_normal_support_message_does_not_enter_shopping_flow():
    state = ShoppingConversationState()
    assert fallback_turn_analysis("hello, how are you?", state).action == "none"


@pytest.mark.anyio
async def test_unrelated_customer_message_does_not_query_catalog_or_create_shopping_state():
    outcome = await process_widget_shopping_turn(
        None, uuid4(), uuid4(), "hello, can someone help with my account?", None, None
    )
    assert not outcome.handled


def test_shopping_context_is_isolated_per_conversation_payload():
    first = state_with_results()
    second = ShoppingConversationState()
    first.intent.category = "phone"
    second.intent.category = "laptop"
    assert first.intent.category != second.intent.category
    assert first.last_displayed_recommendations != second.last_displayed_recommendations


def test_k_budget_is_parsed_as_thousands_for_conversational_refinement():
    state = ShoppingConversationState()
    analysis = fallback_turn_analysis("Show phones under 30k", state)
    assert analysis.action == "start_or_refine"
    assert analysis.intent_patch is not None
    assert analysis.intent_patch.budget_amount == 30000


@pytest.mark.parametrize(
    ("message", "category"),
    [
        ("Do you have a mobile?", "phone"),
        ("Do you sell smartphones?", "phone"),
        ("Any phone available?", "phone"),
        ("Mobile xa?", "phone"),
        ("30 hajar muni phone xa?", "phone"),
        ("Show me a notebook", "laptop"),
        ("TWS cha?", "earbuds"),
        ("television khoj", "tv"),
        ("refrigerator", "fridge"),
    ],
)
def test_product_discovery_phrases_are_routed_as_shopping(message, category):
    assert SHOPPING_CUES.search(message)
    analysis = fallback_turn_analysis(message, ShoppingConversationState())
    assert analysis.action == "start_or_refine"
    assert analysis.intent_patch is not None
    assert analysis.intent_patch.category == category


def test_tool_registry_rejects_unknown_tools_and_extra_fields():
    with pytest.raises(ValueError, match="Unsupported"):
        validate_tool_input("cancel_order", {})
    with pytest.raises(ValueError):
        validate_tool_input("recommend_products", {"intent": {}, "sql": "select 1"})


def test_comparison_tool_accepts_two_to_four_distinct_products_only():
    refs = [ToolReference(product_id=uuid4(), variant_id=uuid4()) for _ in range(4)]
    assert len(CompareProductsInput(products=refs[:2]).products) == 2
    assert len(CompareProductsInput(products=refs).products) == 4
    with pytest.raises(ValueError, match="different products"):
        CompareProductsInput(products=[refs[0], refs[0]])


def test_agent_conversation_contract_contains_only_safe_shopping_context():
    context = state_with_results().model_dump(mode="json")
    row = {
        "id": uuid4(), "organization_id": uuid4(), "ticket_id": uuid4(), "channel": "shopify_widget",
        "status": "active", "ai_mode": "ai", "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC), "shopping_context": context,
    }
    result = ConversationOut.model_validate(row)
    assert result.shopping_context is not None
    assert result.shopping_context.intent["category"] == "phone"

