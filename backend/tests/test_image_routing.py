"""
Task-aware image-model routing.

Quality routing and technical failover are different concepts. Moving the
primary model to the Lite tier on latency evidence alone would have sent five
text-heavy book covers to the tier least suited to exact lettering - and the
controlled comparison confirmed it: Lite rendered "THE THEM" for "The Let
Them Theory" and bled "habits" across a neighbouring cover, while the
higher-quality tier produced "LET THEM THEORY / MEL ROBBINS" and the correct
"ICHIRO KISHIMI and FUMITAKE KOGA".
"""

import pytest

from app.ai_providers.image_routing import (
    ImageTier,
    choose_image_tier,
    provider_for_tier,
)


class _Decision:
    def __init__(self, text, text_class):
        self.text, self.text_class = text, text_class


class _Zone:
    def __init__(self, role):
        self.role = role


class _Contract:
    def __init__(self, roles):
        self.zones = [_Zone(r) for r in roles]


def test_a_plain_scene_uses_the_fast_tier():
    decision = choose_image_tier()
    assert decision.tier is ImageTier.FAST
    assert decision.reasons


def test_text_printed_on_the_product_forces_the_high_quality_tier():
    """The reason Nano Banana was chosen in the first place."""
    decision = choose_image_tier(ownership_decisions=[
        _Decision("Atomic Habits", "product_native"),
    ])
    assert decision.is_high_quality
    assert any("printed on the product" in r for r in decision.reasons)


def test_case02_routes_to_high_quality():
    """
    Five book covers, five distinct identities, dense embedded text. The
    measured comparison showed the fast tier corrupting two of them.
    """
    decision = choose_image_tier(
        ownership_decisions=[
            _Decision(t, "product_native") for t in
            ("Atomic Habits", "The Psychology of Money", "The Let Them Theory",
             "Don't Believe Everything You Think", "The Courage to be Disliked")
        ],
        product_instance_count=5,
        contract=_Contract(["product", "text", "negative-space"]),
    )
    assert decision.is_high_quality
    assert any("dense embedded text" in r for r in decision.reasons)
    assert any("5 distinct product identities" in r for r in decision.reasons)


def test_multiple_products_force_high_quality_even_without_text():
    decision = choose_image_tier(product_instance_count=2)
    assert decision.is_high_quality


def test_a_previous_identity_failure_forces_high_quality():
    decision = choose_image_tier(previously_failed_identity=True)
    assert decision.is_high_quality
    assert any("failed identity validation" in r for r in decision.reasons)


def test_final_output_forces_high_quality():
    assert choose_image_tier(is_final_output=True).is_high_quality


def test_a_draft_stays_fast_even_when_complex():
    """Low-risk iteration should not pay the higher tier."""
    decision = choose_image_tier(
        ownership_decisions=[_Decision("Label", "product_native")],
        product_instance_count=3, is_draft=True,
    )
    assert decision.tier is ImageTier.FAST


def test_high_quality_never_requires_a_technical_failure_first():
    """
    Quality routing happens BEFORE generation. A book cover does not become
    text-heavy because a request timed out.
    """
    decision = choose_image_tier(
        ownership_decisions=[_Decision("Cover", "product_native")]
    )
    assert decision.is_high_quality
    assert not any("error" in r.lower() or "fail" in r.lower()
                   for r in decision.reasons if "identity" not in r)


@pytest.mark.parametrize("role", ["product", "price", "screen", "graphic"])
def test_text_critical_zones_force_high_quality(role):
    decision = choose_image_tier(contract=_Contract([role]))
    assert decision.is_high_quality


def test_a_caption_only_composition_stays_fast():
    assert choose_image_tier(contract=_Contract(["text", "subject"])).tier is ImageTier.FAST


class _Registry:
    def __init__(self, primary, high_quality=None):
        self._p, self._hq = primary, high_quality

    def image_generation(self):
        return self._p

    def image_generation_high_quality(self):
        return self._hq


class _Model:
    def __init__(self, model):
        self.model, self.provider = model, "nano_banana"


def test_the_high_quality_tier_resolves_to_the_configured_model():
    registry = _Registry(_Model("lite"), _Model("preview"))
    decision = choose_image_tier(is_final_output=True)
    provider, escalation_from = provider_for_tier(registry, decision)
    assert provider.model == "preview"
    assert escalation_from.model == "lite"


def test_a_missing_high_quality_model_is_reported_not_silent():
    registry = _Registry(_Model("lite"), None)
    decision = choose_image_tier(is_final_output=True)
    provider, _ = provider_for_tier(registry, decision)
    assert provider.model == "lite"
    assert any("no high-quality model is configured" in r for r in decision.reasons)


def test_the_shipped_config_routes_case02_to_the_preview_tier():
    """End to end against the real registry."""
    from app.ai_providers.registry import default_registry

    decision = choose_image_tier(
        ownership_decisions=[_Decision(f"cover {i}", "product_native") for i in range(5)],
        product_instance_count=5,
    )
    provider, _ = provider_for_tier(default_registry, decision)
    assert provider.provider == "nano_banana"
    assert "preview" in provider.model, "text-heavy work should use the stronger tier"


# ---------------------------------------------------------------------------
# Persisted (dict) shapes.
#
# Both artifacts that feed the router store JSON - TextOwnershipArtifact.
# blocks_json and CompositionContractArtifact.contract_json - so in production
# the router is handed dicts, never the typed objects the tests above use.
# Reading them with getattr alone returned the default every time, which meant
# the router saw NO evidence and sent every creative to the fast tier while
# every test above still passed.
# ---------------------------------------------------------------------------


def test_persisted_ownership_blocks_are_read_as_dicts():
    decision = choose_image_tier(ownership_decisions=[
        {"text": "Atomic Habits", "text_class": "product_native"},
    ])
    assert decision.is_high_quality
    assert any("printed on the product" in r for r in decision.reasons)


def test_persisted_contract_zones_are_read_as_dicts():
    decision = choose_image_tier(contract={"zones": [{"role": "product"}]})
    assert decision.is_high_quality
    assert any("product" in r for r in decision.reasons)


def test_case02_persisted_shape_routes_to_high_quality():
    """The dict equivalent of test_case02_routes_to_high_quality."""
    titles = [
        "The Let Them Theory", "Atomic Habits", "The Psychology of Money",
        "Don't Believe Everything You Think", "The Courage to be Disliked",
    ]
    decision = choose_image_tier(
        ownership_decisions=[
            {"text": t, "text_class": "product_native"} for t in titles
        ],
        contract={"zones": [{"role": "product"}] * 5},
        product_instance_count=5,
    )
    assert decision.is_high_quality
    assert any("dense embedded text" in r for r in decision.reasons)


def test_an_empty_persisted_contract_does_not_crash():
    """A slide analysed before contracts existed has no zones at all."""
    assert choose_image_tier(contract={}).tier is ImageTier.FAST
    assert choose_image_tier(contract={"zones": None}).tier is ImageTier.FAST


def test_a_blank_persisted_text_block_is_not_evidence():
    """An empty string is a block that carries no lettering to preserve."""
    decision = choose_image_tier(ownership_decisions=[
        {"text": "   ", "text_class": "product_native"},
    ])
    assert decision.tier is ImageTier.FAST
