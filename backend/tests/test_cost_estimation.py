"""
Cost estimation tests (Phase 1 remediation, WP-1).

The point of these is that no cost figure is ever MISLEADING. A wrong
number looks authoritative in a report, so "unknown" and "partial" must
be reported honestly rather than smoothed into a plausible float.
"""

import pytest

from app.services.cost_estimation import (
    CostStatus,
    estimate_image_cost,
    estimate_token_cost,
    load_pricing,
    reported_model_for,
)

# A self-contained fixture - these tests must not depend on the real
# pricing.yaml, whose rates legitimately change over time.
PRICING = {
    "pricing": {
        "openai": {
            "gpt-5.5": {
                "reported_model": "gpt-5.5-2026-04-23",
                "per_1k_prompt_tokens": 0.005,
                "per_1k_completion_tokens": 0.030,
            },
            "gpt-image-1": {"per_image": 0.25},
            "prompt-only": {"per_1k_prompt_tokens": 0.005},
        },
        "nano_banana": {
            "gemini-3.1-flash-image-preview": {
                "status": "unknown",
                "reason": "preview variant and pixel basis not established",
            }
        },
    }
}


def test_complete_token_usage_and_rates_is_estimated():
    result = estimate_token_cost("openai", "gpt-5.5", 1000, 1000, pricing=PRICING)
    assert result.status is CostStatus.ESTIMATED
    assert result.amount_usd == pytest.approx(0.005 + 0.030)
    assert result.is_usable is True
    assert result.reason is None


def test_missing_completion_rate_is_partial_not_a_silent_undercount():
    """
    The specific latent bug WP-1 was written around: the old code
    returned a bare number here, indistinguishable from a full estimate.
    """
    result = estimate_token_cost("openai", "prompt-only", 1000, 1000, pricing=PRICING)
    assert result.status is CostStatus.PARTIAL
    assert result.amount_usd == pytest.approx(0.005)  # prompt side only
    assert "missing completion rate" in result.reason
    assert result.is_usable is False, "a known under-count must not be summed as if complete"


def test_missing_token_usage_is_partial_with_a_specific_reason():
    result = estimate_token_cost("openai", "gpt-5.5", 1000, None, pricing=PRICING)
    assert result.status is CostStatus.PARTIAL
    assert "missing completion token usage" in result.reason


def test_no_usage_at_all_is_unknown_not_zero():
    result = estimate_token_cost("openai", "gpt-5.5", None, None, pricing=PRICING)
    assert result.status is CostStatus.UNKNOWN
    assert result.amount_usd is None, "unknown must be None, never 0.0 - 0.0 reads as 'free'"
    assert "no usage data" in result.reason


def test_unconfigured_model_is_unknown_not_zero():
    result = estimate_token_cost("openai", "some-new-model", 100, 100, pricing=PRICING)
    assert result.status is CostStatus.UNKNOWN
    assert result.amount_usd is None
    assert "no pricing.yaml entry" in result.reason


def test_explicitly_unknown_rate_surfaces_its_configured_reason():
    """A model we deliberately could not price must explain why."""
    result = estimate_image_cost(
        "nano_banana", "gemini-3.1-flash-image-preview", pricing=PRICING
    )
    assert result.status is CostStatus.UNKNOWN
    assert result.amount_usd is None
    assert "preview variant" in result.reason


def test_image_cost_multiplies_by_count():
    result = estimate_image_cost("openai", "gpt-image-1", image_count=3, pricing=PRICING)
    assert result.status is CostStatus.ESTIMATED
    assert result.amount_usd == pytest.approx(0.75)


def test_reported_model_is_exposed_for_attribution():
    assert reported_model_for("openai", "gpt-5.5", pricing=PRICING) == "gpt-5.5-2026-04-23"
    assert reported_model_for("openai", "gpt-image-1", pricing=PRICING) is None


# --- Assertions about the REAL shipped pricing.yaml -------------------


def test_real_pricing_file_declares_when_it_was_verified():
    pricing = load_pricing()
    assert pricing.get("rates_verified_on"), "pricing.yaml must record rates_verified_on"


def test_real_pricing_entries_all_carry_a_source_or_an_explicit_unknown():
    """Every entry is either sourced, or honestly marked unknown with a reason."""
    pricing = load_pricing()
    for provider, models in (pricing.get("pricing") or {}).items():
        for model, entry in models.items():
            label = f"{provider}/{model}"
            assert entry.get("source"), f"{label} has no source URL"
            assert entry.get("verified_on"), f"{label} has no verified_on date"
            if entry.get("status") == "unknown":
                assert entry.get("reason"), f"{label} is unknown but gives no reason"
            else:
                has_rate = any(
                    entry.get(k) is not None
                    for k in ("per_1k_prompt_tokens", "per_1k_completion_tokens", "per_image")
                )
                assert has_rate, f"{label} is neither priced nor marked unknown"


def test_the_models_actually_configured_are_all_represented():
    """
    Guards the real failure mode: swapping a model in providers.yaml and
    silently losing cost visibility because pricing.yaml was not updated.
    """
    import yaml

    from app.services.cost_estimation import PRICING_YAML_PATH

    providers_path = PRICING_YAML_PATH.parent / "providers.yaml"
    providers = yaml.safe_load(providers_path.read_text())
    pricing = load_pricing().get("pricing") or {}

    for provider, capabilities in (providers.get("models") or {}).items():
        for capability, model in capabilities.items():
            assert model in pricing.get(provider, {}), (
                f"providers.yaml uses {provider}/{model} for {capability}, "
                "but pricing.yaml has no entry (priced or explicitly unknown) for it"
            )
