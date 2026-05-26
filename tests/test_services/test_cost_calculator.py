import pytest
from backend.services.cost_calculator import calculate_cost


def test_haiku_cost():
    # 1M input @ $0.80 + 1M output @ $4.00 = $4.80
    cost = calculate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert cost == pytest.approx(4.80)


def test_sonnet_cost():
    # 1M input @ $3.00 + 1M output @ $15.00 = $18.00
    cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == pytest.approx(18.00)


def test_unknown_model_falls_back_to_sonnet_rates():
    cost = calculate_cost("future-model", 1_000_000, 1_000_000)
    assert cost == pytest.approx(18.00)


def test_zero_tokens_returns_zero():
    assert calculate_cost("claude-sonnet-4-6", 0, 0) == 0.0


def test_small_real_call():
    # 1000 input + 200 output on haiku
    cost = calculate_cost("claude-haiku-4-5-20251001", 1000, 200)
    expected = (1000 * 0.80 + 200 * 4.00) / 1_000_000
    assert cost == pytest.approx(expected)
