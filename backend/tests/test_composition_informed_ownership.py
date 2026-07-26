"""
Composition-informed ownership (ADR 0001, Package C).

WP-1.5A routed on wording alone, which cannot answer the questions that
actually decide ownership: is this text ON the product, INSIDE a screen, or
merely NEXT TO something? Those are spatial facts, and the Composition
Contract is where they live.

Each test below is one of the failures Package C exists to fix, written as
the question a reviewer would ask rather than as a property of the code.
"""

import pytest

from app.services.profile_schema import OverlayPolicy, TextMode
from app.services.text_classification import TextClass
from app.services.text_ownership import (
    ImageStrategy,
    Owner,
    assert_single_ownership,
    decide_ownership,
)
from tests.benchmark_loader import CASES, load_contract, load_ground_truth

MODE = {
    "designed_typography": TextMode.DESIGNED_TYPOGRAPHY,
    "platform_caption": TextMode.PLATFORM_CAPTION,
}


def block(text, x0, y0, x1, y1, *, surface="overlay"):
    return {
        "text": text,
        "surface": surface,
        "bounding_box": {"x_min": x0, "y_min": y0, "x_max": x1, "y_max": y1},
    }


def only(plan):
    assert len(plan.decisions) == 1
    return plan.decisions[0]


# --------------------------------------------------------------------------
# The five spatial questions Package C was scoped to answer.
# --------------------------------------------------------------------------


def test_text_on_a_product_is_owned_by_product_lock():
    """
    Case 6's tub labels read like ordinary words. Only their position says
    they are printed on the packaging - and re-typesetting packaging is how
    you fabricate a brand that does not exist.
    """
    contract = load_contract("case06_meal_prep")
    left_stack = contract.zone_for((0.10, 0.50, 0.40, 0.60))
    assert left_stack.zone_id == "left-stack"

    decision = only(
        decide_ownership(
            [block("HIGH PROTEIN", 0.10, 0.50, 0.40, 0.60)],
            project_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
            contract=contract,
        )
    )
    assert decision.text_class is TextClass.PRODUCT_NATIVE
    assert decision.owner is Owner.IMAGE
    assert decision.image_strategy is ImageStrategy.PRODUCT_LOCK
    assert decision.composition_zone_id == "left-stack"


def test_the_same_words_off_the_product_stay_designed_typography():
    """
    The control for the test above. If position did not decide it, the two
    would be indistinguishable - which is exactly the WP-1.5A failure.
    """
    contract = load_contract("case06_meal_prep")
    decision = only(
        decide_ownership(
            [block("HIGH PROTEIN", 0.08, 0.26, 0.44, 0.34)],
            project_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
            contract=contract,
        )
    )
    assert decision.text_class is TextClass.DESIGNED_TYPOGRAPHY
    assert decision.owner is Owner.TYPOGRAPHY
    assert decision.composition_zone_id == "left-label"


def test_text_inside_a_screen_belongs_to_the_screen():
    """
    Case 1's weather map. Composite it and you get a caption floating over a
    television; leave it to the image and the television has a screen.
    """
    contract = load_contract("case01_weather_tv")
    decision = only(
        decide_ownership(
            [block("Edinburgh 23", 0.40, 0.20, 0.60, 0.26)],
            project_text_mode=TextMode.PLATFORM_CAPTION,
            contract=contract,
        )
    )
    assert decision.text_class is TextClass.ENVIRONMENTAL
    assert decision.owner is Owner.IMAGE
    assert decision.image_strategy is ImageStrategy.GENERATED
    assert decision.composition_zone_role == "screen"


def test_a_screen_does_not_swallow_the_caption_above_it():
    """The caption sits outside the screen and stays the user's to remove."""
    contract = load_contract("case01_weather_tv")
    decision = only(
        decide_ownership(
            [block("pov: the forecast is lying to you", 0.12, 0.10, 0.88, 0.14)],
            project_text_mode=TextMode.PLATFORM_CAPTION,
            contract=contract,
        )
    )
    assert decision.owner is Owner.CAPTION
    assert decision.composition_zone_id == "caption"


def test_a_shelf_price_is_scene_text_associated_with_its_product():
    """
    Case 8. A price tag is neither packaging nor a caption: it belongs to the
    scene, but it is ABOUT a product. Both halves have to survive - product
    locking a price would print £30 onto the fan's box.
    """
    contract = load_contract("case08_fan_shelf")
    decision = only(
        decide_ownership(
            [block("£30", 0.22, 0.73, 0.40, 0.80, surface="physical")],
            project_text_mode=TextMode.PLATFORM_CAPTION,
            contract=contract,
        )
    )
    assert decision.text_class is TextClass.ENVIRONMENTAL
    assert decision.image_strategy is ImageStrategy.GENERATED
    assert decision.composition_zone_id == "price-label"
    assert "product" in decision.associated_zone_ids, (
        "the price must stay attached to the product it prices"
    )


def test_a_rule_zone_is_designed_typography_the_renderer_owns():
    """
    Case 4's rule under the numeral. It carries no words, so wording could
    never classify it; the contract declares it a `graphic` zone, which is
    what tells the renderer it is theirs to draw and to clear.
    """
    contract = load_contract("case04_posture")
    decision = only(
        decide_ownership(
            [block("", 0.08, 0.232, 0.20, 0.244)],
            project_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
            contract=contract,
        )
    )
    assert decision.text_class is TextClass.DESIGNED_TYPOGRAPHY
    assert decision.owner is Owner.TYPOGRAPHY
    assert decision.composition_zone_id == "numeral-rule"
    assert decision.associated_zone_ids == ["headline", "numeral"]


# --------------------------------------------------------------------------
# Guardrails: composition must not become a second, quieter policy engine.
# --------------------------------------------------------------------------


def test_composition_never_overrides_the_users_overlay_policy():
    """
    ADR §4. Position may decide WHAT a block is; it must never decide what
    the user is allowed to do with their own caption.
    """
    contract = load_contract("case01_weather_tv")
    plan = decide_ownership(
        [block("pov: the forecast is lying to you", 0.12, 0.10, 0.88, 0.14)],
        overlay_policy=OverlayPolicy.REVIEW_INDIVIDUALLY,
        project_text_mode=TextMode.PLATFORM_CAPTION,
        contract=contract,
    )
    assert only(plan).owner is Owner.REVIEW


def test_a_block_in_no_zone_falls_back_to_the_wording_route():
    """
    An incomplete contract must degrade to WP-1.5A behaviour, not to silence.
    Contracts will be partial in production and that cannot lose blocks.
    """
    contract = load_contract("case04_posture")
    assert contract.zone_for((0.90, 0.02, 0.99, 0.05)) is None
    decision = only(
        decide_ownership(
            [block("Your upper back", 0.90, 0.02, 0.99, 0.05)],
            project_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
            contract=contract,
        )
    )
    assert decision.owner is Owner.TYPOGRAPHY
    assert decision.composition_zone_id is None


def test_no_contract_reproduces_wp_1_5a_exactly():
    """Package C is additive. Without a contract, nothing may change."""
    blocks = [
        block("Your upper back", 0.08, 0.26, 0.55, 0.33),
        block("£30", 0.22, 0.73, 0.40, 0.80, surface="physical"),
    ]
    without = decide_ownership(blocks, project_text_mode=TextMode.DESIGNED_TYPOGRAPHY)
    for decision in without.decisions:
        assert decision.composition_zone_id is None
        assert decision.associated_zone_ids == []


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_ownership_stays_single_with_a_contract_applied(case):
    """
    The invariant Package A persists must survive spatial reclassification.
    Moving a block between classes is exactly where a second owner could be
    introduced without anyone noticing.
    """
    truth = load_ground_truth(case)
    blocks = [
        block(entry["text"], 0.1, 0.1 + 0.05 * index, 0.6, 0.14 + 0.05 * index)
        for index, entry in enumerate(truth["text_blocks"])
    ]
    plan = decide_ownership(
        blocks,
        project_text_mode=MODE[truth["primary_text_mode"]],
        contract=load_contract(case),
    )
    assert_single_ownership(plan)
    assert len(plan.decisions) == len(blocks), "every block keeps exactly one decision"
