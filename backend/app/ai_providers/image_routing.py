"""
Task-aware image-model routing.

**Quality routing and technical failover are different concepts**, and
conflating them was a real mistake: the primary model was moved to the Lite
tier on latency evidence alone, which would have sent five text-heavy book
covers to the tier least suited to exact lettering.

Four distinct mechanisms, in order:

1. **Quality routing** (this module) — choose the right tier BEFORE
   generating, from the creative's visual demands.
2. **Technical retry** (`failover.py`) — retry transient errors on the
   chosen model.
3. **Tier escalation** (`failover.py`) — move up the Google tiers.
4. **Emergency fallback** (`failover.py`) — GPT Image, only after the
   Google route genuinely fails.

The higher-quality tier must never require Lite to fail first. A book cover
does not become text-heavy because a request timed out.

## Why this matters for Nano Banana specifically

Nano Banana is the primary generator not merely because it is cheap, but
because it is strong at exact text inside images, packaging, labels, book
covers, product identity and realistic commercial imagery. Routing a
text-critical creative to the fastest tier discards the reason the provider
was chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ImageTier(StrEnum):
    """Which Google image tier a request should use."""

    FAST = "fast"                  # simple scenes, drafts, low-risk iteration
    HIGH_QUALITY = "high_quality"  # text, packaging, identity, final output


#: Zone roles whose presence implies embedded text the model must get right.
_TEXT_CRITICAL_ROLES = frozenset({"product", "price", "screen", "graphic"})

#: Text classes that live ON the product and must survive generation.
_EMBEDDED_TEXT_CLASSES = frozenset({"product_native"})

#: Above this many distinct product instances, identities start competing
#: for the model's attention and the stronger tier earns its cost.
MULTI_PRODUCT_THRESHOLD = 2

#: Product-native text blocks above which the creative counts as dense.
DENSE_TEXT_THRESHOLD = 3


def _get(obj, key: str, default=None):
    """
    Read `key` from an ORM object or a plain dict.

    Both artifacts that feed this module persist as JSON (`blocks_json`,
    `contract_json`), so by the time a decision reaches the router it is
    usually a dict, while the analysis stages hold typed objects. Supporting
    only one shape would mean the router silently saw no evidence in
    production and routed everything to FAST.
    """
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


@dataclass
class RoutingDecision:
    tier: ImageTier
    reasons: list[str] = field(default_factory=list)

    @property
    def is_high_quality(self) -> bool:
        return self.tier is ImageTier.HIGH_QUALITY

    def as_dict(self) -> dict:
        return {"tier": str(self.tier), "reasons": list(self.reasons)}


def choose_image_tier(
    *,
    ownership_decisions=None,
    contract=None,
    product_instance_count: int = 0,
    previously_failed_identity: bool = False,
    is_final_output: bool = False,
    is_draft: bool = False,
) -> RoutingDecision:
    """
    Choose the tier from the creative's demands, before any generation.

    Every input is something analysis has already established, so this costs
    nothing and needs no extra provider call. Reasons are recorded because a
    tier choice that cannot be explained cannot be argued with.

    Biased toward the stronger tier: generating a book cover with garbled
    lettering wastes the whole run, whereas over-spending on a simple scene
    wastes the difference between two tiers.
    """
    reasons: list[str] = []

    if previously_failed_identity:
        reasons.append("a previous candidate failed identity validation")

    if is_final_output:
        reasons.append("high-value final output")

    embedded = [
        d for d in (ownership_decisions or [])
        if str(_get(d, "text_class", "")) in _EMBEDDED_TEXT_CLASSES
        and str(_get(d, "text", "")).strip()
    ]
    if embedded:
        reasons.append(
            f"{len(embedded)} text block(s) printed on the product itself - "
            "exact lettering must survive generation"
        )
    if len(embedded) >= DENSE_TEXT_THRESHOLD:
        reasons.append(f"dense embedded text ({len(embedded)} blocks)")

    if product_instance_count >= MULTI_PRODUCT_THRESHOLD:
        reasons.append(
            f"{product_instance_count} distinct product identities to preserve"
        )

    if contract is not None:
        zones = _get(contract, "zones", []) or []
        roles = {str(_get(zone, "role", "")) for zone in zones}
        critical = sorted(roles & _TEXT_CRITICAL_ROLES)
        if critical:
            reasons.append(f"composition declares {critical} zone(s)")

    if reasons and not is_draft:
        return RoutingDecision(ImageTier.HIGH_QUALITY, reasons)

    if is_draft:
        return RoutingDecision(
            ImageTier.FAST,
            (reasons or []) + ["draft iteration - speed over fidelity"],
        )

    return RoutingDecision(
        ImageTier.FAST,
        ["no embedded product text, single identity, no text-critical zones"],
    )


def provider_for_tier(registry, decision: RoutingDecision):
    """
    Resolve a tier to a configured provider.

    Falls back to the primary when no high-quality model is configured -
    and says so, rather than silently generating at the wrong tier.
    """
    primary = registry.image_generation()
    if not decision.is_high_quality:
        return primary, None

    high_quality = registry.image_generation_high_quality()
    if high_quality is None:
        decision.reasons.append(
            "high quality requested but no high-quality model is configured; "
            "using the primary tier"
        )
        return primary, None
    return high_quality, primary
