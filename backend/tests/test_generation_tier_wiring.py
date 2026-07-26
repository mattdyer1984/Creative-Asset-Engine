"""
Tier routing must actually reach the provider call.

`image_routing` was correct and fully unit-tested, and still had no effect on
a real run. Two separate defects sat between it and the provider:

1. Both artifacts persist as JSON, so the router was handed dicts and read
   them with `getattr` - seeing no evidence and routing everything to FAST.
   Covered in test_image_routing.py.
2. `_route_image_provider` bypassed routing whenever `plan.provider` was set,
   but `decision_engine` sets it unconditionally from the configured primary,
   so it was never empty. Covered here.

Both were invisible to unit tests of the router itself, which is why these
tests assert on the wiring rather than on `choose_image_tier`.

The live evidence: a full Case 2 run generated on `gemini-3.1-flash-lite-image`
while its ownership artifact held 22 `product_native` blocks.
"""

from __future__ import annotations

import pytest

from app.services.decision_engine import GenerationPlan
from app.services.generation_engine import _route_image_provider


class _Provider:
    def __init__(self, provider, model):
        self.provider, self.model = provider, model


class _Registry:
    """Mirrors the real registry's shape: two tiers, one provider."""

    def __init__(self, high_quality=True):
        self._primary = _Provider("nano_banana", "gemini-3.1-flash-lite-image")
        self._hq = (
            _Provider("nano_banana", "gemini-3.1-flash-image-preview")
            if high_quality else None
        )
        self._other = _Provider("openai", "gpt-image-1")

    def image_generation(self, provider_name=None):
        if provider_name in (None, "nano_banana"):
            return self._primary
        return self._other

    def image_generation_high_quality(self):
        return self._hq


class _Slide:
    id = "slide-1"


class _Artifact:
    """Enough of the ORM row for the router; blocks/zones stay JSON."""

    def __init__(self, blocks=None, zones=None):
        self.blocks_json = blocks
        self.contract_json = {"zones": zones} if zones is not None else None


class _DB:
    """Returns the ownership artifact then the contract, as the router asks."""

    def __init__(self, ownership=None, contract=None):
        self._ownership, self._contract = ownership, contract

    def scalars(self, statement):
        text = str(statement)
        row = self._ownership if "text_ownership" in text else self._contract
        return _Scalars(row)


class _Scalars:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


CASE02_BLOCKS = [
    {"text": t, "text_class": "product_native"}
    for t in (
        "Atomic Habits", "James Clear", "The Psychology of Money",
        "Morgan Housel", "THE LET THEM THEORY", "Mel Robbins",
        "THE COURAGE TO BE DISLIKED", "ICHIRO KISHIMI and FUMITAKE KOGA",
        "DON'T BELIEVE EVERYTHING YOU THINK", "Joseph Nguyen",
    )
]
CASE02_ZONES = [{"role": "product"} for _ in range(5)]


@pytest.fixture
def registry(monkeypatch):
    reg = _Registry()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry", reg
    )
    return reg


def _case02_db():
    return _DB(
        ownership=_Artifact(blocks=CASE02_BLOCKS),
        contract=_Artifact(zones=CASE02_ZONES),
    )


def _plan(provider="nano_banana", model="gemini-3.1-flash-lite-image"):
    return GenerationPlan(
        quality_mode="fast", candidate_count=2, provider=provider, model=model,
    )


def test_case02_reaches_the_high_quality_model(registry):
    """
    The regression. `decision_engine` always fills `plan.provider` with the
    primary, so the previous guard returned before routing ever ran and the
    real run generated five text-heavy book covers on the Lite tier.
    """
    provider, decision = _route_image_provider(_case02_db(), _Slide(), _plan())

    assert provider.model == "gemini-3.1-flash-image-preview"
    assert decision is not None and decision.is_high_quality


def test_the_default_provider_being_echoed_back_does_not_disable_routing(registry):
    """Naming the primary is the default, not an operator override."""
    _, decision = _route_image_provider(_case02_db(), _Slide(), _plan())
    assert decision is not None


def test_a_genuinely_different_provider_still_wins(registry):
    """An operator naming another provider outranks tier routing."""
    provider, decision = _route_image_provider(
        _case02_db(), _Slide(), _plan(provider="openai", model="gpt-image-1")
    )
    assert provider.provider == "openai"
    assert decision is None, "an explicit override is not a routed decision"


def test_a_plain_slide_stays_on_the_fast_tier(registry):
    """Routing must not send everything to the expensive model."""
    db = _DB(ownership=_Artifact(blocks=[]), contract=_Artifact(zones=[]))
    provider, decision = _route_image_provider(db, _Slide(), _plan())

    assert provider.model == "gemini-3.1-flash-lite-image"
    assert not decision.is_high_quality


def test_a_slide_with_no_artifacts_does_not_crash(registry):
    """Slides analysed before these artifacts existed still generate."""
    provider, decision = _route_image_provider(_DB(), _Slide(), _plan())
    assert provider.model == "gemini-3.1-flash-lite-image"
    assert not decision.is_high_quality


def test_no_configured_high_quality_model_falls_back_and_says_so(monkeypatch):
    """Silently generating at the wrong tier is the failure to avoid."""
    reg = _Registry(high_quality=False)
    monkeypatch.setattr("app.services.generation_engine.default_registry", reg)

    provider, decision = _route_image_provider(_case02_db(), _Slide(), _plan())

    assert provider.model == "gemini-3.1-flash-lite-image"
    assert any("no high-quality model is configured" in r for r in decision.reasons)
