"""
Graphic Ownership Enforcement (ADR 0001 WP-1.5B, completed in Package D).

Every rendering owner must receive clean, uncontested space before it
renders. The ladder is strict and each rung records why the previous failed -
without that, debugging a bad output means guessing which stage went wrong.

The case-4 red residue is the regression fixture for this package. WP-1.5A
left it in a live end-to-end output and an earlier detector called that
output clean. It must be caught by geometry that would also find case 7's
divider, not by a constant tuned until case 4 passed.
"""

import pathlib
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.services.composition_schema import CompositionContract, Device, Zone, ZoneRole
from app.services.graphic_ownership import (
    LADDER,
    OCCUPANCY_THRESHOLD,
    LadderStep,
    adapt_layout,
    enforce,
    measure_occupancy,
    owner_render_zones,
    reconstruct_zone,
)
from app.services.profile_schema import TextMode
from app.services.text_ownership import decide_ownership
from tests.benchmark_loader import load_contract

CASE04 = pathlib.Path(__file__).parent / "benchmarks" / "case04_posture"
ZONE = (0.1, 0.1, 0.6, 0.3)


def _image(dirty: bool = False) -> bytes:
    canvas = Image.new("RGB", (600, 800), (247, 245, 240))
    if dirty:
        ImageDraw.Draw(canvas).rectangle([70, 95, 350, 130], fill=(150, 20, 30))
    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def _block(text, bounds):
    return {
        "text": text, "surface": "overlay",
        "bounding_box": {
            "x_min": bounds[0], "y_min": bounds[1], "x_max": bounds[2], "y_max": bounds[3],
        },
    }


# --------------------------------------------------------------------------
# Occupancy detection
# --------------------------------------------------------------------------


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


def test_localised_residue_is_not_diluted_by_a_large_zone():
    """A defect can be small in either axis; an average buries both."""
    tall_and_wide = (0.02, 0.05, 0.95, 0.9)
    assert not measure_occupancy(_image(dirty=True), "b", tall_and_wide).is_clean


def test_the_report_says_where_the_defect_is():
    """
    "This zone is dirty" is not actionable. A reviewer has to be sent to the
    pixels, and a later rung needs the region to repair.
    """
    result = measure_occupancy(_image(dirty=True), "b", (0.02, 0.05, 0.95, 0.9))
    assert result.worst_region is not None
    x0, y0, x1, y1 = result.worst_region
    assert x1 > x0 and y1 > y0
    # The defect is the red bar at x 0.117-0.583, y 0.119-0.163. The reported
    # tile must overlap it - a region elsewhere would send a reviewer to the
    # wrong place, which is worse than reporting none at all.
    assert x0 < 0.583 and x1 > 0.117, result.worst_region
    assert y0 < 0.163 and y1 > 0.119, result.worst_region


# --------------------------------------------------------------------------
# Case 4: the regression this package exists to close
# --------------------------------------------------------------------------


def test_case04_residue_is_found_inside_the_contracts_graphic_zone():
    """
    THE Package D regression. The leftover red rule sits entirely outside
    every OCR bounding box, because a rule is a graphic element and OCR only
    reports text. The Composition Contract declares it a `graphic` zone, and
    that is what makes it findable.
    """
    contract = load_contract("case04_posture")
    rule = next(z for z in contract.zones if z.zone_id == "numeral-rule")
    image_bytes = (CASE04 / "e2e_wp15a.png").read_bytes()

    occupancy = measure_occupancy(image_bytes, "numeral-rule", rule.bounds)
    assert not occupancy.is_clean, (
        "the red rule residue in the WP-1.5A end-to-end output must not be "
        "reported clean - it is plainly visible in the image"
    )
    assert occupancy.ink_fraction > OCCUPANCY_THRESHOLD * 5
    # The residue is the right-hand remnant of the original rule, measured at
    # x 0.180-0.205, y 0.233-0.240 in e2e_wp15a.png.
    x0, _, x1, _ = occupancy.worst_region
    assert x1 > 0.15, f"the worst tile should cover the residue, got {occupancy.worst_region}"


def test_case04_empty_space_in_the_same_image_is_still_clean():
    """
    The control. A detector that calls everything dirty catches the residue
    for the wrong reason and would fire on every slide.
    """
    contract = load_contract("case04_posture")
    whitespace = next(z for z in contract.zones if z.zone_id == "whitespace")
    image_bytes = (CASE04 / "e2e_wp15a.png").read_bytes()
    assert measure_occupancy(image_bytes, "whitespace", whitespace.bounds).is_clean


def test_the_rule_zone_is_found_without_any_ocr_block():
    """
    Nothing in the OCR output mentions the rule, so nothing derived from OCR
    can reserve space for it. The contract can.
    """
    contract = load_contract("case04_posture")
    plan = decide_ownership(
        [_block("Your upper back", (0.08, 0.26, 0.55, 0.33))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    zones = owner_render_zones(plan, contract)
    rule = next((z for z in zones if z.zone_id == "numeral-rule"), None)
    assert rule is not None, "the renderer-owned rule must be reserved"
    assert "no text block" in rule.source


@pytest.mark.parametrize("case,zone_id", [("case07_gut_health", "divider")])
def test_the_same_geometry_finds_other_cases_graphic_elements(case, zone_id):
    """
    Generalisation check. Case 7's divider is a different element, in a
    different place, in a differently-shaped creative - and it is found by
    the same rule, with nothing case-specific added.
    """
    contract = load_contract(case)
    plan = decide_ownership(
        [_block("BEFORE", (0.12, 0.29, 0.43, 0.35))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    zones = owner_render_zones(plan, contract)
    assert any(z.zone_id == zone_id for z in zones)


def test_case06_has_no_graphic_zone_and_reserves_nothing_extra():
    """
    The negative control for generalisation: a case with no graphic elements
    must not acquire phantom zones. A rule that fires everywhere is not a
    rule.
    """
    contract = load_contract("case06_meal_prep")
    plan = decide_ownership(
        [_block("HIGH PROTEIN", (0.08, 0.26, 0.44, 0.34))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    zones = owner_render_zones(plan, contract)
    assert all(z.zone_role != "graphic" for z in zones)
    assert [z.zone_id for z in zones] == ["left-label"]


# --------------------------------------------------------------------------
# Render zones come from the contract, not from padded OCR boxes
# --------------------------------------------------------------------------


def test_a_render_zone_prefers_the_contract_over_the_ocr_box():
    contract = load_contract("case04_posture")
    plan = decide_ownership(
        [_block("Your upper back", (0.09, 0.27, 0.50, 0.31))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    headline = next(z for z in owner_render_zones(plan, contract) if z.zone_id == "headline")
    assert headline.bounds == (0.075, 0.250, 0.61, 0.370)
    assert "contract" in headline.source


def test_an_unplaced_block_falls_back_to_its_ocr_bounds():
    """An incomplete contract must degrade, not drop an owner's zone."""
    contract = load_contract("case04_posture")
    outside = (0.90, 0.02, 0.99, 0.05)
    plan = decide_ownership(
        [_block("stray", outside)],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    zone = next(z for z in owner_render_zones(plan, contract) if z.block_id == "block-0")
    assert zone.bounds == outside
    assert "OCR bounds" in zone.source


def test_without_a_contract_only_ocr_zones_exist():
    plan = decide_ownership(
        [_block("Your upper back", (0.09, 0.27, 0.50, 0.31))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
    )
    zones = owner_render_zones(plan, None)
    assert len(zones) == 1
    assert zones[0].zone_id is None


# --------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------


def test_the_ladder_order_is_fixed():
    """Model lettering must never be reached before repair is tried."""
    assert LADDER == (
        LadderStep.REGENERATE,
        LadderStep.RECONSTRUCT,
        LadderStep.ADAPT_LAYOUT,
        LadderStep.MODEL_LETTERING,
        LadderStep.HUMAN_REVIEW,
    )


def _plan_for(bounds):
    return decide_ownership(
        [_block("Your upper back", bounds)], project_text_mode=TextMode.DESIGNED_TYPOGRAPHY
    )


def test_a_clean_zone_stops_at_the_first_rung():
    _, result = enforce(_image(), _plan_for(ZONE))
    assert [a.step for a in result.attempts] == [LadderStep.REGENERATE]
    assert result.attempts[0].succeeded
    assert not result.unresolved


def test_a_dirty_zone_escalates_and_records_why():
    _, result = enforce(_image(dirty=True), _plan_for(ZONE))
    steps = [a.step for a in result.attempts]
    assert steps[0] is LadderStep.REGENERATE and not result.attempts[0].succeeded
    assert LadderStep.RECONSTRUCT in steps
    assert result.attempts[1].previous_failure, "each rung must say why the last failed"


def test_every_attempt_records_what_it_did_and_what_it_cost():
    """
    A ladder you cannot audit is a ladder you cannot trust. Each rung states
    its input zone, its output, how that was validated, and its cost - with
    "made no provider call" distinguished from "cost unknown".
    """
    _, result = enforce(_image(dirty=True), _plan_for(ZONE))
    for attempt in result.attempts:
        assert attempt.input_bounds is not None
        assert attempt.output and attempt.validation
        assert attempt.cost_status in {"no_provider_call", "exact", "estimated", "unknown"}
        if attempt.provider is None:
            assert attempt.cost_status == "no_provider_call"
    assert result.known_cost_subtotal == 0.0
    assert result.unknown_cost_attempts == 0


def test_reconstruction_actually_cleans_the_zone():
    repaired, detail = reconstruct_zone(_image(dirty=True), ZONE)
    assert measure_occupancy(repaired, "b", ZONE).is_clean
    assert "reconstructed" in detail


def test_cleanup_actions_are_recorded_for_the_manifest():
    _, result = enforce(_image(dirty=True), _plan_for(ZONE))
    assert result.cleanup_actions
    assert result.cleanup_actions[0].action == str(LadderStep.RECONSTRUCT)
    assert "->" in result.cleanup_actions[0].detail


def test_disabling_reconstruction_escalates_rather_than_rendering_over_content():
    _, result = enforce(_image(dirty=True), _plan_for(ZONE), allow_reconstruct=False)
    assert result.attempts[-1].step is LadderStep.HUMAN_REVIEW
    assert not result.attempts[-1].succeeded


# --------------------------------------------------------------------------
# Rung 3: layout adaptation
# --------------------------------------------------------------------------


def _zone_of(plan, contract, zone_id):
    return next(z for z in owner_render_zones(plan, contract) if z.zone_id == zone_id)


def test_layout_adaptation_relocates_into_declared_negative_space():
    contract = load_contract("case04_posture")
    plan = decide_ownership(
        [_block("1.", (0.08, 0.13, 0.18, 0.21))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    relocated = adapt_layout(_zone_of(plan, contract, "numeral"), contract)
    assert relocated is not None
    bounds, why = relocated
    whitespace = next(z for z in contract.zones if z.zone_id == "whitespace")
    assert bounds[0] >= whitespace.bounds[0] and bounds[1] >= whitespace.bounds[1]
    assert "whitespace" in why


def test_adaptation_refuses_to_relocate_onto_the_subject():
    """
    Trading a dirty zone for a covered photograph is a worse outcome dressed
    up as a fix. Only negative space is a candidate.
    """
    contract = CompositionContract(
        device=Device.PRODUCT_HERO, device_confidence=1.0,
        zones=[
            Zone(zone_id="hero", role=ZoneRole.SUBJECT, bounds=(0.0, 0.0, 1.0, 1.0)),
            Zone(zone_id="label", role=ZoneRole.TEXT, bounds=(0.1, 0.1, 0.6, 0.3)),
        ],
    )
    plan = decide_ownership(
        [_block("Your upper back", (0.1, 0.1, 0.6, 0.3))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    assert adapt_layout(_zone_of(plan, contract, "label"), contract) is None


def test_adaptation_refuses_a_destination_too_small_to_hold_the_owner():
    """Case 4's headline is wider than the only free space on the slide."""
    contract = load_contract("case04_posture")
    plan = decide_ownership(
        [_block("Your upper back", (0.09, 0.27, 0.50, 0.31))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    assert adapt_layout(_zone_of(plan, contract, "headline"), contract) is None


def test_adaptation_refuses_a_destination_that_is_too_small():
    contract = CompositionContract(
        device=Device.PRODUCT_HERO, device_confidence=1.0,
        zones=[
            Zone(zone_id="label", role=ZoneRole.TEXT, bounds=(0.1, 0.1, 0.9, 0.5)),
            Zone(zone_id="gap", role=ZoneRole.NEGATIVE_SPACE, bounds=(0.0, 0.9, 0.1, 1.0)),
        ],
    )
    plan = decide_ownership(
        [_block("Your upper back", (0.1, 0.1, 0.9, 0.5))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    assert adapt_layout(_zone_of(plan, contract, "label"), contract) is None


def test_an_unfixable_zone_reaches_review_without_model_lettering():
    """
    Rung 4 is withheld deliberately: its failures are invisible until someone
    reads the image, so reaching for it to tidy a dirty zone is worse than
    escalating.
    """
    contract = CompositionContract(
        device=Device.PRODUCT_HERO, device_confidence=1.0,
        zones=[Zone(zone_id="label", role=ZoneRole.TEXT, bounds=(0.0, 0.0, 1.0, 1.0))],
    )
    plan = decide_ownership(
        [_block("Your upper back", (0.0, 0.0, 1.0, 1.0))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    _, result = enforce(_image(dirty=True), plan, contract)
    steps = [a.step for a in result.attempts]
    assert LadderStep.MODEL_LETTERING in steps
    assert not next(a for a in result.attempts if a.step is LadderStep.MODEL_LETTERING).succeeded
    assert steps[-1] is LadderStep.HUMAN_REVIEW
    assert result.unresolved == ["block-0"]


# --------------------------------------------------------------------------
# A render zone is a footprint, not "the region this block is near"
# --------------------------------------------------------------------------


def test_blocks_sharing_a_text_column_reserve_it_once():
    """
    Several blocks legitimately share a column. Enforcing the same region once
    per block would reconstruct it repeatedly, each pass working on the last
    pass's output for no gain.
    """
    contract = load_contract("case04_posture")
    plan = decide_ownership(
        [_block("Your upper back", (0.09, 0.26, 0.55, 0.30)),
         _block("feels rounded", (0.09, 0.31, 0.55, 0.35))],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    assert len(plan.renderer_owned) == 2
    headline_zones = [z for z in owner_render_zones(plan, contract) if z.zone_id == "headline"]
    assert len(headline_zones) == 1


def test_a_block_inside_a_subject_zone_does_not_claim_the_subject():
    """
    The zone says what a block is placed AGAINST, which is not the space it
    will be drawn into. Adopting a subject zone as a render footprint would
    have enforcement reconstruct someone's face to make room for a label -
    far worse than the residue it was clearing.
    """
    contract = load_contract("case07_gut_health")
    own_box = (0.30, 0.50, 0.60, 0.56)
    plan = decide_ownership(
        [_block("overlay note", own_box)],
        project_text_mode=TextMode.DESIGNED_TYPOGRAPHY, contract=contract,
    )
    decision = plan.decisions[0]
    assert decision.composition_zone_id == "face", "the contract still records where it sits"

    zone = next(z for z in owner_render_zones(plan, contract) if z.block_id == decision.block_id)
    assert zone.bounds == own_box, "the footprint is the block's own box"
    face = next(z for z in contract.zones if z.zone_id == "face")
    assert zone.bounds != face.bounds
    assert "placed against" in zone.source
