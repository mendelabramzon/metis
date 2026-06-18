"""Per-model pricing (USD per 1M input/output tokens) for cost estimation.

Cached from the claude-api reference (2026-06). Unknown models return ``None`` so
cost is recorded as unavailable rather than wrong.
"""

from __future__ import annotations

_PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    rates = _PRICING.get(model)
    if rates is None:
        return None
    return input_tokens / 1_000_000 * rates[0] + output_tokens / 1_000_000 * rates[1]
