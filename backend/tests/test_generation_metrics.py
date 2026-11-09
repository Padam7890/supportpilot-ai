"""Generation metrics must be bounded and never leak prompt or credentials."""
import json
import logging
from unittest.mock import patch

from app.features.ai.application.generation_metrics import (
    log_generation_metrics,
    normalized_token_totals,
    estimated_generation_cost_usd,
    sanitized_token_usage,
)


def test_usage_rejects_bool_negative_and_unrecognized_fields() -> None:
    assert sanitized_token_usage({
        "input_tokens": 120, "output_tokens": 30,
        "total_tokens": True, "prompt_tokens": -1,
        "completion_tokens": 10_000_001,
        "secret_prompt": "private customer order",
    }) == {"input_tokens": 120, "output_tokens": 30}


def test_missing_usage_is_safe() -> None:
    assert sanitized_token_usage(None) == {}


def test_metric_log_omits_private_usage_fields(caplog) -> None:
    with patch("app.features.ai.application.generation_metrics.monotonic", return_value=3.5):
        with caplog.at_level(logging.INFO, logger="app.features.ai.application.generation_metrics"):
            log_generation_metrics(
                execution_id="execution-1",
                execution_kind="widget_reply",
                model_name="test-model",
                started_monotonic=1.0,
                usage={"input_tokens": 15, "prompt": "secret", "api_key": "never-log"},
                streamed=True,
                correlation_id="trace-1",
            )
    record = next(record for record in caplog.records if "ai_generation_metrics " in record.message)
    data = json.loads(record.message.split("ai_generation_metrics ", 1)[1])
    assert data["duration_ms"] == 2500
    assert data["usage"] == {"input_tokens": 15, "output_tokens": None, "total_tokens": None}
    assert data["cost_usd"] is None
    assert "secret" not in record.message
    assert "never-log" not in record.message


def test_alias_token_counters_are_not_double_counted() -> None:
    assert normalized_token_totals({
        "input_tokens": 40, "prompt_tokens": 40,
        "output_tokens": 10, "completion_tokens": 10,
    }) == {"input_tokens": 40, "output_tokens": 10, "total_tokens": 50}


def test_missing_provider_usage_is_not_guessed() -> None:
    assert normalized_token_totals(None) == {
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
    }


def test_reported_total_is_preserved() -> None:
    assert normalized_token_totals({
        "input_tokens": 80, "output_tokens": 20, "total_tokens": 105,
    }) == {"input_tokens": 80, "output_tokens": 20, "total_tokens": 105}


def test_generation_cost_uses_decimal_and_configured_prices() -> None:
    assert estimated_generation_cost_usd(
        {"prompt_tokens": 1000, "completion_tokens": 500},
        input_price_per_million=0.15, output_price_per_million=0.60,
    ) == "0.00045000"


def test_generation_cost_requires_both_prices_and_counters() -> None:
    assert estimated_generation_cost_usd(
        {"prompt_tokens": 1000}, input_price_per_million=0.15,
        output_price_per_million=0.60,
    ) is None
    assert estimated_generation_cost_usd(
        {"prompt_tokens": 1000, "completion_tokens": 100},
        input_price_per_million=None, output_price_per_million=0.60,
    ) is None


def test_generation_cost_rejects_invalid_price_values() -> None:
    for price in (-1, float("nan"), float("inf")):
        assert estimated_generation_cost_usd(
            {"input_tokens": 100, "output_tokens": 100},
            input_price_per_million=price, output_price_per_million=0.60,
        ) is None
