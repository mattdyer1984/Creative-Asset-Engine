"""
Text ownership and routing (ADR 0001 WP-1.5A).

One inspectable answer to "who is responsible for rendering this text?".
Routing used to be implicit, which is how a block ended up owned twice - the
model rendered the caption because it was in the reference image, and the
Rendering Engine composited it again on top.
"""

import pathlib

import pytest
import yaml

from app.services.profile_schema import OverlayPolicy, TextMode
from app.services.text_ownership import (
    DuplicateOwnership,
    HandlingPolicy,
    Owner,
    assert_single_ownership,
    decide_ownership,
)

BENCHMARKS = pathlib.Path(__file__).parent / "benchmarks"
MODE = {
    "designed_typography": TextMode.DESIGNED_TYPOGRAPHY,
    "platform_caption": TextMode.PLATFORM_CAPTION,
}
IMAGE_OWNED = {Owner.IMAGE}
EXPECTED_OWNER = {
    "deterministic_typography": Owner.TYPOGRAPHY,
    "deterministic_overlay": Owner.CAPTION,
    "product_lock": Owner.IMAGE,
    "model_generated": Owner.IMAGE,
}


def _plan_for(case: str):
    truth = yaml.safe_load((BENCHMARKS / case / "ground_truth.yaml").read_text())
    blocks = [
        {
            "text": b["text"],
            "surface": "physical" if b["class"] in ("product_native", "environmental") else "overlay",
        }
        for b in truth["text_blocks"]
    ]
    return truth, decide_ownership(blocks, project_text_mode=MODE[truth["primary_text_mode"]])


@pytest.mark.parametrize(
    "case", ["case04_posture", "case08_fan_shelf", "case02_books", "case01_weather_tv"]
)
def test_every_block_lands_in_the_right_ownership_class(case):
    """
    The routing consequence - does this text stay with the image, or does a
    renderer draw it? - must be right for every block. Exact owner within
    the image-owned pair needs product-attachment geometry we do not have
    until the Composition Contract.
    """
    truth, plan = _plan_for(case)
    for decision, expected in zip(plan.decisions, truth["text_blocks"], strict=True):
        want = EXPECTED_OWNER[expected["expected_handling_mechanism"]]
        if want in IMAGE_OWNED:
            assert decision.owner in IMAGE_OWNED, f"{decision.text!r} escaped image ownership"
        else:
            assert decision.owner is want, f"{decision.text!r} -> {decision.owner}, want {want}"


@pytest.mark.parametrize(
    "case", ["case04_posture", "case08_fan_shelf", "case02_books", "case01_weather_tv"]
)
def test_no_block_is_owned_twice(case):
    """ADR §4 acceptance criterion 3."""
    _, plan = _plan_for(case)
    assert_single_ownership(plan)


def test_designed_typography_never_reaches_the_caption_renderer():
    """The regression that produced generic white-stroke headlines."""
    _, plan = _plan_for("case04_posture")
    assert all(d.owner is Owner.TYPOGRAPHY for d in plan.decisions)
    assert not any(d.owner is Owner.CAPTION for d in plan.decisions)


def test_product_native_text_is_never_stripped_or_re_typeset():
    """ADR §6: reconstructing branded packaging would fabricate it."""
    _, plan = _plan_for("case02_books")
    covers = [d for d in plan.decisions if d.owner is Owner.IMAGE]
    assert len(covers) == 5
    assert all(d.handling_policy is HandlingPolicy.PRESERVE_VISUAL_ROLE for d in covers)
    assert all(not d.is_renderer_owned for d in covers)


def test_environmental_text_is_not_composited_by_the_caption_renderer():
    """A weather map is part of the scene, not an overlay on it."""
    _, plan = _plan_for("case01_weather_tv")
    screen = [d for d in plan.decisions if "Lerwick" in d.text or d.text == "Thursday"]
    assert screen
    assert all(d.is_image_owned for d in screen)


def test_the_model_is_told_exactly_which_copy_not_to_render():
    """
    Pre-generation half of the no-duplication rule. Checking afterwards tells
    you it went wrong; naming the copy up front is what stops it.
    """
    _, plan = _plan_for("case04_posture")
    owned = plan.texts_the_model_must_not_render()
    assert "Your upper back" in owned
    assert "feels rounded" in owned
    _, caption_plan = _plan_for("case02_books")
    assert "All 5 books for the price of 1 right now" in caption_plan.texts_the_model_must_not_render()


def test_overlay_policy_only_ever_touches_captions():
    """A user's control over their own post must not reach the creative."""
    _, plan = _plan_for("case04_posture")
    review = decide_ownership(
        [{"text": d.text, "surface": "overlay"} for d in plan.decisions],
        overlay_policy=OverlayPolicy.REVIEW_INDIVIDUALLY,
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
    )
    assert all(d.owner is Owner.TYPOGRAPHY for d in review.decisions)


def test_review_individually_routes_captions_to_a_human():
    plan = decide_ownership(
        [{"text": "when ur paying £30 for this...", "surface": "overlay"}],
        overlay_policy=OverlayPolicy.REVIEW_INDIVIDUALLY,
        project_text_mode=TextMode.PLATFORM_CAPTION,
    )
    assert plan.decisions[0].owner is Owner.REVIEW


def test_unsignalled_blocks_take_the_project_default_not_review():
    """
    Benchmark 4's bullets fire no pattern at all. Routing every such block to
    review would flood the queue with text the project already answers for -
    falling through to a documented default is not the same as uncertainty.
    """
    plan = decide_ownership(
        [{"text": "Shoulders keep falling forward", "surface": "overlay"}],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
    )
    assert plan.decisions[0].owner is Owner.TYPOGRAPHY
    assert not plan.needs_review


def test_duplicate_ownership_is_detected():
    plan = decide_ownership(
        [{"text": "Buy now", "surface": "overlay"}], project_text_mode=TextMode.PLATFORM_CAPTION
    )
    duplicated = plan.model_copy(deep=True)
    duplicated.decisions.append(
        plan.decisions[0].model_copy(update={"owner": Owner.TYPOGRAPHY})
    )
    with pytest.raises(DuplicateOwnership):
        assert_single_ownership(duplicated)
