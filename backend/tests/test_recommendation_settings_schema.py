import pytest
from pydantic import ValidationError

from app.schemas.recommendation_settings import RecommendationSettingsIn


def test_recommendation_settings_validate_supported_policy_values():
    settings = RecommendationSettingsIn(
        max_products=5,
        mode="explicit",
        ranking_preferences={"feature_match": 45, "brand": 10},
        human_handoff_preferences={"enabled": True, "rejected_threshold": 4},
    )
    assert settings.max_products == 5
    assert settings.mode == "explicit"


@pytest.mark.parametrize("payload", [
    {"max_products": 0},
    {"max_products": 6},
    {"mode": "always"},
    {"ranking_preferences": {"sql": 100}},
    {"ranking_preferences": {"brand": 101}},
    {"human_handoff_preferences": {"rejected_threshold": 0}},
    {"not_a_setting": True},
])
def test_recommendation_settings_reject_invalid_values(payload):
    with pytest.raises(ValidationError):
        RecommendationSettingsIn.model_validate(payload)


def test_recommendation_settings_deduplicate_collection_ids():
    settings = RecommendationSettingsIn(excluded_collection_ids=[" summer ", "summer", "winter"])
    assert settings.excluded_collection_ids == ["summer", "winter"]
