from __future__ import annotations

COST_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,  # 1.25× input rate
        "cache_read": 0.08,  # 0.10× input rate
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,  # 1.25× input rate
        "cache_read": 0.30,  # 0.10× input rate
    },
}

_FALLBACK = {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    *,
    batch: bool = False,
) -> float:
    """Compute total cost in USD including optional prompt cache tokens.

    batch=True applies the Anthropic Batch API 50% discount to input and output tokens.
    Cache token rates are unchanged (Batch API does not support prompt caching).
    """
    rates = COST_PER_MILLION.get(model, _FALLBACK)
    multiplier = 0.5 if batch else 1.0
    return (
        input_tokens * rates["input"] * multiplier
        + output_tokens * rates["output"] * multiplier
        + cache_creation_tokens * rates["cache_write"]
        + cache_read_tokens * rates["cache_read"]
    ) / 1_000_000
