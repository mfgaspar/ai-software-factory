"""An estimate of what a Claude run has cost so far, while it runs.

Claude Code reports the real cost only in its final result, so a running step has no figure
to show. This estimates one from the token counts and the model's API list price. It is
only for display: limits, records and summaries use the cost Claude reports. On a
subscription plan both are notional API-price figures.

Prices are US dollars per million tokens (Anthropic first-party API, 2026-11). A cache write
is billed at 1.25 times the input price (the 5-minute cache).
"""

from __future__ import annotations

from typing import NamedTuple


class Price(NamedTuple):
    input: float
    output: float
    cache_read: float


CACHE_WRITE = 1.25  # times the input price

# Longest prefix first, so ``claude-opus-5-5`` isn't read as ``claude-opus-5``.
PRICES: dict[str, Price] = {
    "claude-fable-5-2": Price(8.00, 40.00, 0.20),
    "claude-mythos-5-2": Price(8.00, 40.00, 0.20),
    "claude-fable-5-1": Price(10.00, 50.00, 1.00),
    "claude-mythos-5-1": Price(10.00, 50.00, 1.00),
    "claude-fable-5": Price(10.00, 50.00, 1.00),
    "claude-opus-5-5": Price(4.00, 20.00, 0.20),
    "claude-opus-5": Price(5.00, 25.00, 0.50),
    "claude-opus-4-8": Price(5.00, 25.00, 0.50),
    "claude-opus-4-7": Price(5.00, 25.00, 0.50),
    "claude-opus-4-6": Price(5.00, 25.00, 0.50),
    "claude-opus-4-5": Price(5.00, 25.00, 0.50),
    "claude-opus-4": Price(15.00, 75.00, 1.50),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.10),
    "claude-sonnet-5": Price(2.00, 10.00, 0.20),
    "claude-sonnet-4": Price(3.00, 15.00, 0.30),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01),
    "claude-haiku-4-5": Price(1.00, 5.00, 0.10),
}
_BY_LENGTH = sorted(PRICES, key=len, reverse=True)


def price(model: str | None) -> Price | None:
    """The price of ``model`` (an id such as ``claude-opus-4-8[1m]`` or a dated one), or
    None when it isn't known."""
    if not model:
        return None
    model = model.lower().removeprefix("anthropic.")
    return next((PRICES[p] for p in _BY_LENGTH if model.startswith(p)), None)


def estimate(
    model: str | None,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """The list-price cost of these tokens on ``model``, 0.0 when the model isn't known."""
    p = price(model)
    if p is None:
        return 0.0
    total = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * p.input * CACHE_WRITE
    )
    return total / 1_000_000
