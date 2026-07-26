"""
Where the destination platform's own UI sits, and what that costs the
creative.

Every other layout rule in this system is derived from the source creative.
This one is not: it is a property of the app the image will be *displayed
in*, and it is invisible in the image itself. A recreation can be a perfect
copy of the source and still fail, because the pixels it drew are underneath
the platform's own chrome or pointing away from the thing it wants tapped.

**TikTok's buy box sits in the bottom LEFT.** So a call-to-action graphic
placed at the bottom - the pointing emoji, the arrow, the "tap below" - has
to be left-justified. Centred or right-aligned, it directs attention at
empty chrome, and the creative's single most important instruction misses.

## Why this is not inferable from the creative

The Composition Contract already records the source's own placement. For
case02 that is `emoji-row` at `[0.20, 0.82, 0.55, 0.90]` - left-justified,
because whoever made it knew where the buy box was. The contract stores the
*position* but not the *reason*, so nothing downstream could tell that the
position was load-bearing rather than incidental, and both recreations of
that creative drifted: one centred the arrows, the other put "Tap below
before it's gone" in the bottom right. Both are faithful-looking images that
would not work.

This module supplies the missing reason.

## On the thresholds

`BOTTOM_BAND_TOP` and `LEFT_JUSTIFIED_MAX_X0` are judgement calls, and are
deliberately loose. They are set from the one piece of real evidence
available - the case02 ground truth above, whose emoji row has `x0 = 0.20`
and a vertical centre of `0.86` - with margin on both sides. They are a
detector for "clearly at the bottom" and "clearly not left-justified", not a
precise model of TikTok's layout.

**The buy box's exact bounds are NOT recorded here.** Only its corner is,
because only the corner is something known rather than measured. A specific
rectangle would look like a measurement nobody took.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Platform(StrEnum):
    TIKTOK = "tiktok"


class Corner(StrEnum):
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


class Alignment(StrEnum):
    LEFT = "left"
    CENTRE = "centre"
    RIGHT = "right"


#: Which corner each platform's purchase affordance occupies.
BUY_BOX_CORNER: dict[Platform, Corner] = {
    Platform.TIKTOK: Corner.BOTTOM_LEFT,
}

#: A zone whose vertical centre falls below this is "at the bottom".
#: case02's ground-truth emoji row centres at 0.86.
BOTTOM_BAND_TOP = 0.75

#: A bottom CTA is left-justified if it starts within the left third.
#: case02's ground-truth emoji row starts at 0.20.
LEFT_JUSTIFIED_MAX_X0 = 0.35

#: Zone roles that can carry a call to action. `text` is included because
#: the case02 contract types its pointing-emoji row as `text` - the role
#: vocabulary has no dedicated CTA member, and narrowing this to
#: graphic/callout would miss the exact case that prompted the rule.
CTA_ROLES = frozenset({"graphic", "callout", "text"})


def alignment_for(platform: Platform = Platform.TIKTOK) -> Alignment:
    """Which way a bottom CTA must be justified to reach the buy box."""
    corner = BUY_BOX_CORNER[platform]
    return Alignment.LEFT if corner is Corner.BOTTOM_LEFT else Alignment.RIGHT


@dataclass(frozen=True)
class Violation:
    zone_id: str
    message: str


def _bounds(zone) -> tuple[float, float, float, float] | None:
    raw = zone.get("bounds") if isinstance(zone, dict) else getattr(zone, "bounds", None)
    if raw is None or len(raw) != 4:
        return None
    return tuple(float(v) for v in raw)  # type: ignore[return-value]


def _role(zone) -> str:
    value = zone.get("role") if isinstance(zone, dict) else getattr(zone, "role", "")
    return str(value)


def _zone_id(zone) -> str:
    value = zone.get("id") if isinstance(zone, dict) else getattr(zone, "id", "")
    return str(value)


def is_bottom_zone(zone) -> bool:
    bounds = _bounds(zone)
    if bounds is None:
        return False
    _, y0, _, y1 = bounds
    return (y0 + y1) / 2 >= BOTTOM_BAND_TOP


def is_left_justified(zone) -> bool:
    bounds = _bounds(zone)
    return bounds is not None and bounds[0] <= LEFT_JUSTIFIED_MAX_X0


def buy_box_violations(contract, platform: Platform = Platform.TIKTOK) -> list[Violation]:
    """
    Bottom CTA zones that point away from the buy box.

    Reports rather than corrects. Moving a zone here would change the
    composition behind the layout stages' backs; the contract's own
    enforcement path is where a fix belongs, and a caller that only wants to
    know is not forced to accept a rewrite.
    """
    if alignment_for(platform) is not Alignment.LEFT:
        return []

    zones = (contract.get("zones") if isinstance(contract, dict)
             else getattr(contract, "zones", None)) or []

    violations = []
    for zone in zones:
        if _role(zone) not in CTA_ROLES or not is_bottom_zone(zone):
            continue
        if is_left_justified(zone):
            continue
        bounds = _bounds(zone)
        violations.append(Violation(
            zone_id=_zone_id(zone),
            message=(
                f"bottom call-to-action starts at x={bounds[0]:.2f}; TikTok's "
                f"buy box is {BUY_BOX_CORNER[platform]}, so it must start at "
                f"x<={LEFT_JUSTIFIED_MAX_X0} to point at it"
            ),
        ))
    return violations


def placement_instruction(platform: Platform = Platform.TIKTOK) -> str:
    """
    The constraint, as an instruction for the image model.

    Stated as a reason and not only a rule: a bare "left-align the arrows"
    competes with every other layout instruction in the compiled prompt,
    whereas the reason survives being paraphrased.
    """
    corner = BUY_BOX_CORNER[platform]
    side = "left" if corner is Corner.BOTTOM_LEFT else "right"
    return (
        f"PLATFORM LAYOUT: this image is for {platform.value.upper()}, whose "
        f"buy button sits in the {corner.value} of the screen. Any pointing "
        f"emoji, arrow, or 'tap below' call-to-action at the bottom of the "
        f"image MUST be positioned in the bottom {side} and aligned to the "
        f"{side} edge, so it points at the buy button. Do not centre it and "
        f"do not place it on the opposite side - it would direct attention "
        f"at empty interface."
    )
