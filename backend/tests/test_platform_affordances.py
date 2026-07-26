"""
The buy box is bottom left, so a bottom CTA must be too.

Every case here is anchored to the case02 ground truth, which is the only
real evidence available for where a working creative puts its pointer:

    emoji-row  role=text  bounds=[0.20, 0.82, 0.55, 0.90]

and to the two recreations that violated it - one centring the arrows, one
placing "Tap below before it's gone" in the bottom right.
"""

from __future__ import annotations

import pytest

from app.services.platform_affordances import (
    Alignment,
    Platform,
    alignment_for,
    buy_box_violations,
    is_bottom_zone,
    is_left_justified,
    placement_instruction,
)

GROUND_TRUTH_EMOJI_ROW = {
    "id": "emoji-row", "role": "text", "bounds": [0.20, 0.82, 0.55, 0.90],
}
CENTRED_ARROWS = {
    "id": "emoji-row", "role": "graphic", "bounds": [0.38, 0.84, 0.62, 0.92],
}
BOTTOM_RIGHT_CTA = {
    "id": "cta", "role": "callout", "bounds": [0.55, 0.86, 0.95, 0.95],
}
CAPTION = {"id": "caption", "role": "text", "bounds": [0.14, 0.14, 0.86, 0.28]}


def test_tiktok_buy_box_forces_left_alignment():
    assert alignment_for(Platform.TIKTOK) is Alignment.LEFT


def test_the_ground_truth_emoji_row_is_compliant():
    """If the rule flagged the real creative, the rule would be wrong."""
    assert is_bottom_zone(GROUND_TRUTH_EMOJI_ROW)
    assert is_left_justified(GROUND_TRUTH_EMOJI_ROW)
    assert buy_box_violations({"zones": [GROUND_TRUTH_EMOJI_ROW]}) == []


def test_centred_arrows_are_a_violation():
    """The Lite recreation."""
    violations = buy_box_violations({"zones": [CENTRED_ARROWS]})
    assert len(violations) == 1
    assert violations[0].zone_id == "emoji-row"
    assert "buy box is bottom-left" in violations[0].message


def test_a_bottom_right_cta_is_a_violation():
    """The high-quality recreation."""
    violations = buy_box_violations({"zones": [BOTTOM_RIGHT_CTA]})
    assert len(violations) == 1
    assert violations[0].zone_id == "cta"


def test_a_top_caption_is_not_a_bottom_cta():
    """The rule is about the bottom band, not about everything left of centre."""
    assert not is_bottom_zone(CAPTION)
    assert buy_box_violations({"zones": [CAPTION]}) == []


def test_a_full_width_product_row_is_not_flagged():
    """Only CTA-capable roles are candidates."""
    products = {"id": "books", "role": "product", "bounds": [0.1, 0.8, 0.9, 0.95]}
    assert buy_box_violations({"zones": [products]}) == []


def test_the_case02_contract_as_a_whole_passes():
    contract = {"zones": [CAPTION, GROUND_TRUTH_EMOJI_ROW]}
    assert buy_box_violations(contract) == []


def test_zones_are_read_as_objects_too():
    """Contracts reach this both as ORM JSON and as parsed schema objects."""

    class _Zone:
        id, role, bounds = "cta", "graphic", [0.6, 0.85, 0.95, 0.95]

    class _Contract:
        zones = [_Zone()]

    assert len(buy_box_violations(_Contract())) == 1


def test_a_zone_without_bounds_is_skipped_not_crashed():
    assert buy_box_violations({"zones": [{"id": "x", "role": "graphic"}]}) == []


def test_an_empty_contract_is_not_a_violation():
    assert buy_box_violations({}) == []
    assert buy_box_violations({"zones": []}) == []


def test_the_instruction_states_the_side_and_the_reason():
    text = placement_instruction(Platform.TIKTOK)
    assert "bottom-left" in text
    assert "buy button" in text
    assert "Do not centre it" in text


@pytest.mark.parametrize("x0,compliant", [
    (0.00, True), (0.20, True), (0.35, True), (0.36, False), (0.50, False),
])
def test_the_left_justification_boundary(x0, compliant):
    zone = {"id": "cta", "role": "graphic", "bounds": [x0, 0.85, x0 + 0.3, 0.93]}
    assert is_left_justified(zone) is compliant
