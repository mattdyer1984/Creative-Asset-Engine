"""
Estimated API cost computation (Optimisation & Stability Pass, Tier 2.2 -
see MIGRATION_PLAN.md).

Reads backend/pricing.yaml - a small, explicit config the user owns and
keeps current, not a set of invented numbers: no rate below comes from
this codebase's own knowledge of provider pricing, since that changes
over time and getting it silently wrong would be worse than leaving a
null estimated_cost_usd. A provider/model with no entry in pricing.yaml
simply produces None here, never a guess.
"""

from pathlib import Path

import yaml

PRICING_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "pricing.yaml"


def load_pricing(path: Path = PRICING_YAML_PATH) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def estimate_token_cost_usd(
    provider: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    *,
    pricing: dict | None = None,
) -> float | None:
    """
    None whenever pricing.yaml has no rate for this provider/model (the
    common case until the user fills one in), or no token counts were
    captured for this call at all - never a guessed cost.
    """
    if prompt_tokens is None and completion_tokens is None:
        return None

    rates = pricing if pricing is not None else load_pricing()
    prompt_rate = rates.get("per_1k_prompt_tokens", {}).get(provider, {}).get(model)
    completion_rate = rates.get("per_1k_completion_tokens", {}).get(provider, {}).get(model)
    if prompt_rate is None and completion_rate is None:
        return None

    cost = 0.0
    if prompt_tokens is not None and prompt_rate is not None:
        cost += (prompt_tokens / 1000) * prompt_rate
    if completion_tokens is not None and completion_rate is not None:
        cost += (completion_tokens / 1000) * completion_rate
    return cost


def estimate_image_cost_usd(
    provider: str, model: str, *, image_count: int = 1, pricing: dict | None = None
) -> float | None:
    """None whenever pricing.yaml has no per-image rate for this provider/model."""
    rates = pricing if pricing is not None else load_pricing()
    per_image_rate = rates.get("per_image", {}).get(provider, {}).get(model)
    if per_image_rate is None:
        return None
    return per_image_rate * image_count
