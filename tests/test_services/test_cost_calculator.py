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


def test_cache_write_costs_1_25x_input():
    """Cache creation tokens are priced at 1.25× normal input rate."""
    # Haiku input rate: $0.80/M → cache write: $1.00/M
    cost = calculate_cost("claude-haiku-4-5-20251001", 0, 0, cache_creation_tokens=1_000_000)
    assert cost == pytest.approx(1.00)


def test_cache_read_costs_0_10x_input():
    """Cache read tokens are priced at 0.10× normal input rate."""
    # Haiku input rate: $0.80/M → cache read: $0.08/M
    cost = calculate_cost("claude-haiku-4-5-20251001", 0, 0, cache_read_tokens=1_000_000)
    assert cost == pytest.approx(0.08)


def test_full_call_with_cache_mix():
    """A call with input + cache_write + cache_read + output tokens prices correctly."""
    # Sonnet: input $3/M, output $15/M, cache_write $3.75/M, cache_read $0.30/M
    cost = calculate_cost(
        "claude-sonnet-4-6",
        input_tokens=1_000_000,      # $3.00
        output_tokens=1_000_000,     # $15.00
        cache_creation_tokens=1_000_000,  # $3.75
        cache_read_tokens=1_000_000,      # $0.30
    )
    assert cost == pytest.approx(22.05)


def test_unknown_model_cache_fallback():
    """Unknown model falls back to Sonnet cache rates."""
    cost = calculate_cost("unknown-model", 0, 0, cache_read_tokens=1_000_000)
    assert cost == pytest.approx(0.30)  # Sonnet cache_read = $0.30/M
