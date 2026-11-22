from decimal import Decimal

import pytest

from src.agent import pricing
from src.config import settings


@pytest.fixture(autouse=True)
def no_configured_prices(monkeypatch):
    monkeypatch.setattr(settings, "llm_price_input_per_mtok", None)
    monkeypatch.setattr(settings, "llm_price_output_per_mtok", None)


def test_free_tier_model_costs_zero_and_is_flagged():
    assert pricing.cost_for("gemini-3.1-flash-lite", 1000, 500) == Decimal(0)
    assert pricing.is_free_tier("gemini-3.1-flash-lite-preview")


def test_unknown_model_cost_is_unknown_not_zero():
    assert pricing.cost_for("some-paid-model", 1000, 500) is None
    assert not pricing.is_free_tier("some-paid-model")


def test_configured_price_is_used_for_any_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_price_input_per_mtok", 3.0)
    monkeypatch.setattr(settings, "llm_price_output_per_mtok", 15.0)
    # 1M in * $3 + 0.5M out * $15 = $10.50
    assert pricing.cost_for("some-paid-model", 1_000_000, 500_000) == Decimal("10.5")
    assert not pricing.is_free_tier("gemini-3.1-flash-lite")


def test_missing_token_usage_gives_unknown_cost():
    assert pricing.cost_for("gemini-3.1-flash-lite", None, 10) is None
