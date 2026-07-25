"""
Unit tests for app.services.cost_estimation (Optimisation & Stability
Pass, Tier 2.2, see MIGRATION_PLAN.md). Every test passes its own
`pricing` dict rather than touching the real backend/pricing.yaml, per
that module's own design (an explicit override param exists exactly so
callers - including tests - don't need a real file on disk).
"""

import pytest

from app.services.cost_estimation import estimate_image_cost_usd, estimate_token_cost_usd

_PRICING = {
    "per_1k_prompt_tokens": {"openai": {"gpt-5.5": 0.002}},
    "per_1k_completion_tokens": {"openai": {"gpt-5.5": 0.008}},
    "per_image": {"nano_banana": {"gemini-3.1-flash-image-preview": 0.05}},
}


def test_estimate_token_cost_usd_computes_from_both_rates():
    cost = estimate_token_cost_usd("openai", "gpt-5.5", 1000, 500, pricing=_PRICING)

    assert cost == 0.002 * 1 + 0.008 * 0.5


def test_estimate_token_cost_usd_none_when_no_rate_configured():
    assert estimate_token_cost_usd("gemini", "gemini-pro-latest", 1000, 500, pricing=_PRICING) is None


def test_estimate_token_cost_usd_none_when_no_tokens_captured():
    assert estimate_token_cost_usd("openai", "gpt-5.5", None, None, pricing=_PRICING) is None


def test_estimate_token_cost_usd_handles_partial_token_counts():
    """Only prompt_tokens known (e.g. a provider that didn't report completion_tokens) - still computes what it can."""
    cost = estimate_token_cost_usd("openai", "gpt-5.5", 1000, None, pricing=_PRICING)

    assert cost == 0.002


def test_estimate_image_cost_usd_computes_flat_rate_times_count():
    cost = estimate_image_cost_usd(
        "nano_banana", "gemini-3.1-flash-image-preview", image_count=3, pricing=_PRICING
    )

    assert cost == pytest.approx(0.15)


def test_estimate_image_cost_usd_none_when_no_rate_configured():
    assert estimate_image_cost_usd("openai", "gpt-image-1", pricing=_PRICING) is None


def test_empty_pricing_dict_never_crashes():
    assert estimate_token_cost_usd("openai", "gpt-5.5", 100, 50, pricing={}) is None
    assert estimate_image_cost_usd("openai", "gpt-image-1", pricing={}) is None
