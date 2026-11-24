"""The live cost estimate: prices by model id, and what the mapper reports mid-run."""

from __future__ import annotations

import pytest

from compose.engines.base import UsageEvent
from compose.engines.claude import pricing
from compose.engines.claude.mapping import EventMapper


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-opus-5-5", pricing.PRICES["claude-opus-5-5"]),
        ("claude-opus-5", pricing.PRICES["claude-opus-5"]),
        ("claude-opus-4-8[1m]", pricing.PRICES["claude-opus-4-8"]),
        ("claude-haiku-4-5-20251001", pricing.PRICES["claude-haiku-4-5"]),
        ("anthropic.claude-sonnet-5-5", pricing.PRICES["claude-sonnet-5-5"]),
        ("claude-sonnet-4-6", pricing.PRICES["claude-sonnet-4"]),
        ("gpt-5", None),
        (None, None),
    ],
)
def test_price_matches_the_longest_prefix(model: str | None, expected: object) -> None:
    assert pricing.price(model) == expected


def test_estimate_prices_each_kind_of_token() -> None:
    cost = pricing.estimate(
        "claude-opus-5-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=1_000_000,
    )
    assert cost == pytest.approx(4.00 + 20.00 + 0.20 + 5.00)
    assert pricing.estimate("unknown-model", input_tokens=10**6) == 0.0


def test_the_mapper_estimates_from_tokens_and_written_text() -> None:
    mapper = EventMapper()
    line = {
        "type": "assistant",
        "message": {
            "id": "m1",
            "model": "claude-sonnet-5-5",
            "content": [{"type": "text", "text": "x" * 4000}],  # ~1000 output tokens
            "usage": {"input_tokens": 2, "output_tokens": 4, "cache_read_input_tokens": 100_000},
        },
    }
    (*_, event) = mapper.map_json(line)
    assert isinstance(event, UsageEvent)
    assert event.usage.cost_usd == 0.0
    expected = (2 * 2.00 + 1000 * 10.00 + 100_000 * 0.10) / 1_000_000
    assert event.usage.estimated_cost_usd == pytest.approx(expected)
