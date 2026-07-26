"""
Graphic Ownership Enforcement (ADR 0001 WP-1.5B).

Every rendering owner must receive clean, uncontested space before it
renders. The ladder is strict and each rung records why the previous failed -
without that, debugging a bad output means guessing which stage went wrong.
"""

from io import BytesIO

from PIL import Image, ImageDraw

from app.services.graphic_ownership import (
    LADDER,
    OCCUPANCY_THRESHOLD,
    LadderStep,
    enforce,
    measure_occupancy,
    reconstruct_zone,
    render_zone,
)

ZONE = (0.1, 0.1, 0.6, 0.3)


def _image(dirty: bool = False) -> bytes:
    canvas = Image.new("RGB", (600, 800), (247, 245, 240))
    if dirty:
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([70, 95, 350, 130], fill=(150, 20, 30))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_clean_zone_is_reported_clean():
    assert measure_occupancy(_image(), "b", ZONE).is_clean


def test_an_occupied_zone_is_detected():
    result = measure_occupancy(_image(dirty=True), "b", ZONE)
    assert not result.is_clean
    assert result.ink_fraction > OCCUPANCY_THRESHOLD


def test_the_threshold_separates_clean_from_residue_by_a_wide_margin():
    """
    Set from measurement, not taste. An earlier value of 0.06 sat above the
    real case-4 residue and declared it clean - a visible defect passing an
    automated check.
    """
    clean = measure_occupancy(_image(), "b", ZONE).ink_fraction
    dirty = measure_occupancy(_image(dirty=True), "b", ZONE).ink_fraction
    assert clean < OCCUPANCY_THRESHOLD < dirty
    assert dirty > clean * 10


def test_localised_residue_is_not_diluted_by_a_tall_zone():
    """
    Averaging over a whole zone hides a small defect. The case-4 rule residue
    measures 0.052 in its own band and far less spread across a tall zone,
    which is how it survived an earlier version of this check.
    """
    tall = (0.1, 0.05, 0.6, 0.9)
    assert not measure_occupancy(_image(dirty=True), "b", tall).is_clean


def test_the_ladder_order_is_fixed():
    """Model lettering must never be reached before repair is tried."""
    assert LADDER == (
        LadderStep.REGENERATE, LadderStep.RECONSTRUCT, LadderStep.ADAPT_LAYOUT,
        LadderStep.MODEL_LETTERING, LadderStep.HUMAN_REVIEW,
    )
    assert LADDER.index(LadderStep.MODEL_LETTERING) > LADDER.index(LadderStep.RECONSTRUCT)


def test_a_clean_zone_stops_at_the_first_rung():
    _, result = enforce(_image(), [("b", ZONE)])
    assert [a.step for a in result.attempts] == [LadderStep.REGENERATE]
    assert result.attempts[0].succeeded
    assert not result.cleanup_actions


def test_a_dirty_zone_escalates_and_records_why():
    _, result = enforce(_image(dirty=True), [("b", ZONE)])
    steps = [a.step for a in result.attempts]
    assert steps[0] is LadderStep.REGENERATE and not result.attempts[0].succeeded
    assert LadderStep.RECONSTRUCT in steps
    reconstruct = next(a for a in result.attempts if a.step is LadderStep.RECONSTRUCT)
    assert reconstruct.previous_failure, "every rung must say why the previous one failed"
    assert "occupied" in reconstruct.previous_failure


def test_reconstruction_actually_cleans_the_zone():
    before = measure_occupancy(_image(dirty=True), "b", ZONE)
    repaired, detail = reconstruct_zone(_image(dirty=True), ZONE)
    after = measure_occupancy(repaired, "b", ZONE)
    assert after.ink_fraction < before.ink_fraction
    assert "reconstructed" in detail


def test_cleanup_actions_are_recorded_for_the_manifest():
    _, result = enforce(_image(dirty=True), [("b", ZONE)])
    assert result.cleanup_actions
    assert result.cleanup_actions[0].action == str(LadderStep.RECONSTRUCT)
    assert "->" in result.cleanup_actions[0].detail


def test_disabling_reconstruction_escalates_rather_than_rendering_over_content():
    _, result = enforce(_image(dirty=True), [("b", ZONE)], allow_reconstruct=False)
    assert result.attempts[-1].step is LadderStep.HUMAN_REVIEW
    assert not result.attempts[-1].succeeded
    assert "b" in result.unresolved


def test_a_rule_bearing_role_reserves_space_below_its_text():
    """
    A rule is drawn below the text box, and OCR never reports it because a
    rule is a graphic element rather than text.
    """
    text_only = render_zone((0.1, 0.1, 0.5, 0.2))
    with_rule = render_zone((0.1, 0.1, 0.5, 0.2), has_rule=True)
    assert with_rule[3] > text_only[3]
    assert with_rule[:3] == text_only[:3]
