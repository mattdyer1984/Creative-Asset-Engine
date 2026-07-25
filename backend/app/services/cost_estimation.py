"""
Estimated API cost computation (Phase 1 remediation, WP-1/WP-2).

Reads backend/pricing.yaml. No rate in this module comes from the
codebase's own knowledge of provider pricing - every figure is config,
sourced and dated in that file, because getting a price silently wrong
is worse than having none: a wrong number still looks authoritative in
a report.

**Why the result carries a status and a reason, not just a float.**
The previous version returned a bare `float | None` and accumulated each
side of a token-billed call independently:

    if prompt_tokens and prompt_rate:      cost += ...
    if completion_tokens and completion_rate: cost += ...

so a call with a prompt rate but no completion rate returned a NUMBER -
a systematic under-count, indistinguishable from a complete estimate. A
boolean `is_estimated` could not express that either. Hence CostStatus:

  exact     - the provider reported an authoritative billed amount.
              Nothing does today; reserved so the vocabulary need not
              widen later.
  estimated - complete usage x a configured, sourced rate. The normal
              good case.
  partial   - a real number, but a known UNDER-COUNT: some component of
              the call is uncosted. `reason` says which.
  unknown   - no defensible figure at all; `amount_usd` is None.

`reason` is required for partial and unknown, because an unqualified
"partial" is useless when auditing spend months later.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

PRICING_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "pricing.yaml"


class CostStatus(StrEnum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CostEstimate:
    amount_usd: float | None
    status: CostStatus
    reason: str | None = None

    @property
    def is_usable(self) -> bool:
        """True when the figure can be summed without misleading anyone."""
        return self.status in (CostStatus.EXACT, CostStatus.ESTIMATED)


def load_pricing(path: Path = PRICING_YAML_PATH) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _model_entry(pricing: dict, provider: str, model: str) -> dict | None:
    return (pricing.get("pricing") or {}).get(provider, {}).get(model)


def reported_model_for(provider: str, model: str, *, pricing: dict | None = None) -> str | None:
    """
    What the provider actually serves for this identifier, where known -
    aliases (gemini-flash-latest) and dated snapshots (gpt-5.5-2026-04-23)
    differ from what we request, and spend needs attributing to the real
    thing.
    """
    rates = pricing if pricing is not None else load_pricing()
    entry = _model_entry(rates, provider, model) or {}
    return entry.get("reported_model")


def estimate_token_cost(
    provider: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    *,
    pricing: dict | None = None,
) -> CostEstimate:
    rates = pricing if pricing is not None else load_pricing()
    entry = _model_entry(rates, provider, model)

    if entry is None:
        return CostEstimate(
            None,
            CostStatus.UNKNOWN,
            f"no pricing.yaml entry for {provider}/{model}",
        )
    if entry.get("status") == "unknown":
        reason = (entry.get("reason") or "").strip().replace("\n", " ")
        return CostEstimate(
            None,
            CostStatus.UNKNOWN,
            f"rate explicitly unknown for {provider}/{model}: {reason}" if reason
            else f"rate explicitly unknown for {provider}/{model}",
        )

    prompt_rate = entry.get("per_1k_prompt_tokens")
    completion_rate = entry.get("per_1k_completion_tokens")

    if prompt_tokens is None and completion_tokens is None:
        return CostEstimate(
            None, CostStatus.UNKNOWN, "provider returned no usage data for this call"
        )
    if prompt_rate is None and completion_rate is None:
        return CostEstimate(
            None, CostStatus.UNKNOWN, f"no token rates configured for {provider}/{model}"
        )

    cost = 0.0
    gaps: list[str] = []

    if prompt_tokens is not None:
        if prompt_rate is not None:
            cost += (prompt_tokens / 1000) * prompt_rate
        else:
            gaps.append("missing prompt rate")
    else:
        gaps.append("missing prompt token usage")

    if completion_tokens is not None:
        if completion_rate is not None:
            cost += (completion_tokens / 1000) * completion_rate
        else:
            gaps.append("missing completion rate")
    else:
        gaps.append("missing completion token usage")

    if gaps:
        return CostEstimate(
            cost,
            CostStatus.PARTIAL,
            "under-counted: " + "; ".join(gaps),
        )
    return CostEstimate(cost, CostStatus.ESTIMATED)


def estimate_image_cost(
    provider: str, model: str, *, image_count: int = 1, pricing: dict | None = None
) -> CostEstimate:
    rates = pricing if pricing is not None else load_pricing()
    entry = _model_entry(rates, provider, model)

    if entry is None:
        return CostEstimate(
            None, CostStatus.UNKNOWN, f"no pricing.yaml entry for {provider}/{model}"
        )
    if entry.get("status") == "unknown":
        reason = (entry.get("reason") or "").strip().replace("\n", " ")
        return CostEstimate(
            None,
            CostStatus.UNKNOWN,
            f"rate explicitly unknown for {provider}/{model}: {reason}" if reason
            else f"rate explicitly unknown for {provider}/{model}",
        )

    per_image = entry.get("per_image")
    if per_image is None:
        return CostEstimate(
            None, CostStatus.UNKNOWN, f"no per-image rate configured for {provider}/{model}"
        )
    return CostEstimate(per_image * image_count, CostStatus.ESTIMATED)


# --- Backwards-compatible shims -------------------------------------
# app/stages/execution.py and generation_engine.py still call the old
# float-returning helpers. They keep working unchanged; WP-2 migrates
# those call sites to the richer CostEstimate when ProviderCall lands.


def estimate_token_cost_usd(
    provider: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    *,
    pricing: dict | None = None,
) -> float | None:
    return estimate_token_cost(
        provider, model, prompt_tokens, completion_tokens, pricing=pricing
    ).amount_usd


def estimate_image_cost_usd(
    provider: str, model: str, *, image_count: int = 1, pricing: dict | None = None
) -> float | None:
    return estimate_image_cost(provider, model, image_count=image_count, pricing=pricing).amount_usd
