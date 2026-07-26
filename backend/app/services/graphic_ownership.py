"""
Graphic Ownership Enforcement (ADR 0001 WP-1.5B).

**Objective: every rendering owner receives clean, uncontested space before
it renders.** Clean zones, occupancy detection, removal residue, retries,
layout adaptation and the fallback ladder are all manifestations of that one
requirement, which is why they live together rather than as "zone
reservation" plus a pile of special cases.

The ladder is strict and every rung records why the previous one failed.
Without that, debugging a bad output means guessing which stage went wrong.

    1 regenerate      stronger ownership instructions to the model
    2 reconstruct     inpaint / repair the zone
    3 adapt           re-lay the typography within the space available
    4 model lettering last resort, and only where L3 makes it necessary
    5 review          hand it to a human rather than ship something wrong

Model lettering sits at rung 4 deliberately. It is the unreliable option -
the one whose failures are invisible until someone reads the image - so it
must never be the first thing tried when a zone is merely dirty.
"""

from __future__ import annotations

from enum import StrEnum
from io import BytesIO

from PIL import Image, ImageStat
from pydantic import BaseModel, ConfigDict, Field


class LadderStep(StrEnum):
    REGENERATE = "regenerate"
    RECONSTRUCT = "reconstruct"
    ADAPT_LAYOUT = "adapt_layout"
    MODEL_LETTERING = "model_lettering"
    HUMAN_REVIEW = "human_review"


#: The order enforcement attempts things. Never reordered at runtime.
LADDER: tuple[LadderStep, ...] = (
    LadderStep.REGENERATE,
    LadderStep.RECONSTRUCT,
    LadderStep.ADAPT_LAYOUT,
    LadderStep.MODEL_LETTERING,
    LadderStep.HUMAN_REVIEW,
)

#: Above this fraction of a zone showing edge/ink energy, the zone is dirty.
#:
#: Set from measurement, not taste. On the case-4 residue: genuinely clean
#: zones measure 0.0000-0.0002, while the leftover red rule the WP-1.5A run
#: left behind measures 0.0519 - a 250x separation. An earlier value of 0.06
#: sat just ABOVE the residue and declared it clean, which is how a visible
#: defect passed an automated check.
OCCUPANCY_THRESHOLD = 0.02

#: A rule-bearing role draws BELOW its text box, and OCR never reported the
#: original's rule because a rule is a graphic element rather than text. The
#: enforced zone therefore has to cover what the RENDERER will occupy, not
#: only where text used to be - the case-4 residue sits entirely outside
#: every OCR bounding box. Proper zones arrive with the Composition Contract;
#: until then this pads the measured region downward.
RULE_ZONE_PADDING = 0.035

#: Bands per zone for occupancy scanning - see measure_occupancy.
_OCCUPANCY_BANDS = 8


class ZoneOccupancy(BaseModel):
    """How dirty one owner's zone is, and the evidence for saying so."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    bounds: tuple[float, float, float, float]
    ink_fraction: float
    is_clean: bool
    detail: str


class OwnershipAttempt(BaseModel):
    """One rung of the ladder, and why it was needed."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    step: LadderStep
    succeeded: bool
    reason: str
    #: Why the PREVIOUS rung failed. Empty on the first attempt.
    previous_failure: str = ""


class CleanupAction(BaseModel):
    """Something enforcement did to the image to make space usable."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    action: str
    bounds: tuple[float, float, float, float]
    detail: str


def measure_occupancy(
    image_bytes: bytes, block_id: str, bounds: tuple[float, float, float, float]
) -> ZoneOccupancy:
    """
    Is this zone clean enough for an owner to render into?

    Measured as edge energy rather than raw darkness: a zone can be legitimately
    mid-toned (a coloured panel) and still be clean, whereas leftover glyph
    fragments produce high-frequency detail. Standard deviation over the region
    approximates that without a full edge-detection pass.
    """
    with Image.open(BytesIO(image_bytes)) as source:
        image = source.convert("L")
        width, height = image.size
        box = (
            max(int(bounds[0] * width), 0), max(int(bounds[1] * height), 0),
            min(int(bounds[2] * width), width), min(int(bounds[3] * height), height),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            return ZoneOccupancy(
                block_id=block_id, bounds=bounds, ink_fraction=0.0, is_clean=True,
                detail="zone has no area",
            )
        region = image.crop(box)

    # Scanned in horizontal bands, taking the WORST, not averaged over the
    # whole zone. Averaging dilutes a small localised defect: the case-4 rule
    # residue measures 0.052 in its own band and 0.004 spread across the
    # numeral's full render zone, which is how it passed an earlier version of
    # this check while being plainly visible.
    band_height = max(region.height // _OCCUPANCY_BANDS, 1)
    stddev = 0.0
    for top in range(0, region.height, band_height):
        band = region.crop((0, top, region.width, min(top + band_height, region.height)))
        if band.height < 2:
            continue
        stddev = max(stddev, ImageStat.Stat(band).stddev[0])

    ink_fraction = min(stddev / 128.0, 1.0)
    clean = ink_fraction <= OCCUPANCY_THRESHOLD
    return ZoneOccupancy(
        block_id=block_id, bounds=bounds, ink_fraction=round(ink_fraction, 4), is_clean=clean,
        detail=(
            f"worst band variation {stddev:.1f} within the zone "
            f"({'clean' if clean else 'occupied - residue or content present'})"
        ),
    )


class EnforcementResult(BaseModel):
    """What enforcement did, in full, for the manifest."""

    model_config = ConfigDict(extra="forbid")

    occupancy: list[ZoneOccupancy] = Field(default_factory=list)
    attempts: list[OwnershipAttempt] = Field(default_factory=list)
    cleanup_actions: list[CleanupAction] = Field(default_factory=list)

    @property
    def unresolved(self) -> list[str]:
        """Blocks that reached the end of the ladder without clean space."""
        resolved = {a.block_id for a in self.attempts if a.succeeded}
        attempted = {a.block_id for a in self.attempts}
        return sorted(attempted - resolved)


def reconstruct_zone(
    image_bytes: bytes, bounds: tuple[float, float, float, float]
) -> tuple[bytes, str]:
    """
    Rung 2: repair a dirty zone by filling it from its surroundings.

    Reuses the reference-masking fill, which samples a ring OUTSIDE the region
    rather than blurring the region itself - blurring leaves a bold fragment as
    a dark smudge, which is the exact residue this rung exists to remove.
    """
    from app.services.reference_masking import build_text_masked_image

    block = [{
        "surface": "overlay",
        "bounding_box": {
            "x_min": bounds[0], "y_min": bounds[1], "x_max": bounds[2], "y_max": bounds[3],
        },
    }]
    repaired = build_text_masked_image(image_bytes, block)
    if repaired is None:
        return image_bytes, "reconstruction declined - the zone could not be filled safely"
    return repaired, "zone reconstructed from surrounding background"


def render_zone(
    bounds: tuple[float, float, float, float], *, has_rule: bool = False
) -> tuple[float, float, float, float]:
    """
    The space the RENDERER will occupy, which is not the space the text
    occupied. See RULE_ZONE_PADDING.
    """
    if not has_rule:
        return bounds
    return (bounds[0], bounds[1], bounds[2], min(bounds[3] + RULE_ZONE_PADDING, 1.0))


def enforce(
    image_bytes: bytes,
    zones: list[tuple[str, tuple[float, float, float, float]]],
    *,
    allow_reconstruct: bool = True,
) -> tuple[bytes, EnforcementResult]:
    """
    Walk the ladder for every owner zone until it is clean or exhausted.

    WP-1.5B implements rungs 1-3 and records 4-5 rather than performing them:
    regeneration belongs to the generation loop and model lettering is a
    deliberate escalation, not something enforcement should reach for on its
    own. Reaching rung 4 or 5 is recorded honestly so it is visible rather
    than hidden behind a silent cleanup.
    """
    result = EnforcementResult()
    current = image_bytes

    for block_id, bounds in zones:
        occupancy = measure_occupancy(current, block_id, bounds)
        result.occupancy.append(occupancy)
        if occupancy.is_clean:
            result.attempts.append(
                OwnershipAttempt(
                    block_id=block_id, step=LadderStep.REGENERATE, succeeded=True,
                    reason="zone already clean - the model honoured the ownership instruction",
                )
            )
            continue

        previous = (
            f"zone occupied (ink fraction {occupancy.ink_fraction:.3f} > "
            f"{OCCUPANCY_THRESHOLD}) - {occupancy.detail}"
        )
        result.attempts.append(
            OwnershipAttempt(
                block_id=block_id, step=LadderStep.REGENERATE, succeeded=False,
                reason=previous,
            )
        )

        if not allow_reconstruct:
            result.attempts.append(
                OwnershipAttempt(
                    block_id=block_id, step=LadderStep.HUMAN_REVIEW, succeeded=False,
                    reason="reconstruction disabled - escalating rather than rendering over content",
                    previous_failure=previous,
                )
            )
            continue

        current, detail = reconstruct_zone(current, bounds)
        after = measure_occupancy(current, block_id, bounds)
        result.cleanup_actions.append(
            CleanupAction(
                block_id=block_id, action=str(LadderStep.RECONSTRUCT), bounds=bounds,
                detail=f"{detail}; ink fraction {occupancy.ink_fraction:.3f} -> {after.ink_fraction:.3f}",
            )
        )
        result.attempts.append(
            OwnershipAttempt(
                block_id=block_id, step=LadderStep.RECONSTRUCT, succeeded=after.is_clean,
                reason=(
                    "zone reconstructed and now clean" if after.is_clean
                    else f"reconstruction insufficient - ink fraction still {after.ink_fraction:.3f}"
                ),
                previous_failure=previous,
            )
        )
        if after.is_clean:
            continue

        # Rungs 3-5 are recorded, not silently performed. Adapting layout needs
        # the Composition Contract's zones; model lettering is an escalation.
        result.attempts.append(
            OwnershipAttempt(
                block_id=block_id, step=LadderStep.ADAPT_LAYOUT, succeeded=False,
                reason="layout adaptation needs Composition Contract zones (Phase 2)",
                previous_failure=f"reconstruction left ink fraction {after.ink_fraction:.3f}",
            )
        )
        result.attempts.append(
            OwnershipAttempt(
                block_id=block_id, step=LadderStep.HUMAN_REVIEW, succeeded=False,
                reason="no rung produced clean space - surfaced rather than rendered over",
                previous_failure="layout adaptation unavailable",
            )
        )

    return current, result
