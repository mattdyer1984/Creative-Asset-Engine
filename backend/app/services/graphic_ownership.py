"""
Graphic Ownership Enforcement (ADR 0001 WP-1.5B, completed in Package D).

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

**What Package D changed.** WP-1.5B measured padded OCR boxes, which cannot
work: the defect it was built to catch is a rule the OCR never reported,
because a rule is a graphic element and not text. Padding a text box downward
by a constant happened to cover case 4 and generalises to nothing. Render
zones now come from the Composition Contract, which declares graphic elements
as zones in their own right - so the same code finds a divider in case 7 and
a rule in case 4 without either being special.
"""

from __future__ import annotations

from enum import StrEnum
from io import BytesIO

from PIL import Image, ImageStat
from pydantic import BaseModel, ConfigDict, Field

from app.services.composition_schema import CompositionContract, ZoneRole
from app.services.text_ownership import OwnershipPlan


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

#: Above this fraction of tile variation, a zone is dirty.
#:
#: Set from measurement, not taste. Measured on the case-4 end-to-end output:
#: genuinely empty space reads 0.0032, while the leftover red rule reads
#: 0.2472 - a 77x separation. An earlier value of 0.06 sat just above the
#: residue and declared it clean, which is how a visible defect passed an
#: automated check.
OCCUPANCY_THRESHOLD = 0.02

#: Occupancy is scanned as a grid, not averaged and not banded only by row.
#: A defect can be localised in EITHER axis: case 4's residue occupies the
#: right-hand fifth of its zone and about a third of its height, so a whole-
#: zone average buries it and a row-band scan only half-recovers it.
_OCCUPANCY_ROWS = 4
_OCCUPANCY_COLS = 6

#: Zone roles a deterministic renderer owns outright. `graphic` is the reason
#: this list exists: rules, dividers and design marks carry no text, so they
#: are invisible to OCR and to anything that reasons from OCR.
RENDERER_OWNED_ROLES = frozenset({ZoneRole.GRAPHIC})

#: Roles whose zone IS the render footprint. A text block sitting in a `text`
#: zone will be drawn across that zone, so the zone is the right thing to
#: clean. A block sitting in a `subject` zone is merely LOCATED there - the
#: zone is a person, or a photograph. Adopting it as the render footprint
#: would have enforcement reconstruct someone's face to make room for a
#: caption, which is a far worse outcome than the residue it was clearing.
_FOOTPRINT_ROLES = frozenset({ZoneRole.TEXT, ZoneRole.CAPTION, ZoneRole.GRAPHIC})


class ZoneOccupancy(BaseModel):
    """How dirty one owner's zone is, and the evidence for saying so."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    bounds: tuple[float, float, float, float]
    ink_fraction: float
    is_clean: bool
    detail: str
    #: Where inside the zone the worst tile sat, normalised to the IMAGE.
    #: A reviewer needs to be sent to the defect, not merely told a zone is
    #: dirty - "somewhere in this column" is not a usable report.
    worst_region: tuple[float, float, float, float] | None = None


class OwnershipAttempt(BaseModel):
    """One rung of the ladder: what it did, and what it cost."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    step: LadderStep
    succeeded: bool
    reason: str
    #: Why the PREVIOUS rung failed. Empty on the first attempt.
    previous_failure: str = ""
    #: The zone this rung was given to work on.
    input_bounds: tuple[float, float, float, float] | None = None
    #: What it produced, and how that was checked - separately, because a
    #: rung that ran is not the same as a rung that worked.
    output: str = ""
    validation: str = ""
    #: Paid work, if any. `None` means this rung made no provider call at all,
    #: which is different from a call whose cost is unknown.
    provider: str | None = None
    cost_usd: float | None = None
    cost_status: str = "no_provider_call"


class CleanupAction(BaseModel):
    """Something enforcement did to the image to make space usable."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    action: str
    bounds: tuple[float, float, float, float]
    detail: str


class RenderZone(BaseModel):
    """Space one owner will draw into, and where that claim came from."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    bounds: tuple[float, float, float, float]
    zone_id: str | None = None
    zone_role: str | None = None
    source: str


def owner_render_zones(
    plan: OwnershipPlan, contract: CompositionContract | None
) -> list[RenderZone]:
    """
    Every region a deterministic renderer will occupy on this slide.

    Two sources, and the second is the point of Package D:

    1. Zones cited by renderer-owned text decisions - the contract's own
       geometry rather than a padded OCR box.
    2. Renderer-owned zones with NO text block at all. A rule under a heading
       is owned by the typography system, is never reported by OCR, and is
       exactly where case 4's residue sits. Deriving it from the contract is
       what makes finding it general rather than a case-4 special case.

    Falls back to bounds for a decision the contract does not place, so an
    incomplete contract degrades rather than dropping an owner's zone.
    """
    zones: list[RenderZone] = []
    claimed: set[str] = set()

    for decision in plan.renderer_owned:
        if decision.composition_zone_id and contract is not None:
            zone = next(
                (z for z in contract.zones if z.zone_id == decision.composition_zone_id),
                None,
            )
            # One zone, one render zone. Several blocks legitimately share a
            # text column, and enforcing the same region once per block would
            # reconstruct it repeatedly - each pass working on the previous
            # pass's output, for no gain.
            if zone is not None and zone.zone_id in claimed:
                continue
            if zone is not None and zone.role in _FOOTPRINT_ROLES:
                claimed.add(zone.zone_id)
                zones.append(
                    RenderZone(
                        block_id=decision.block_id, bounds=zone.bounds,
                        zone_id=zone.zone_id, zone_role=str(zone.role),
                        source="composition contract zone cited by the decision",
                    )
                )
                continue
        if decision.bounds is not None:
            zones.append(
                RenderZone(
                    block_id=decision.block_id, bounds=decision.bounds,
                    zone_id=decision.composition_zone_id,
                    zone_role=decision.composition_zone_role,
                    source=(
                        f"OCR bounds - the block sits in a "
                        f"{decision.composition_zone_role!r} zone, which is what it is "
                        f"placed against rather than the space it will be drawn into"
                        if decision.composition_zone_role
                        else "OCR bounds - the contract did not place this block"
                    ),
                )
            )

    if contract is None:
        return zones

    for zone in contract.zones:
        if zone.role in RENDERER_OWNED_ROLES and zone.zone_id not in claimed:
            zones.append(
                RenderZone(
                    block_id=f"zone:{zone.zone_id}", bounds=zone.bounds,
                    zone_id=zone.zone_id, zone_role=str(zone.role),
                    source="renderer-owned graphic zone with no text block - "
                           "invisible to OCR, so only the contract declares it",
                )
            )
    return zones


def measure_occupancy(
    image_bytes: bytes, block_id: str, bounds: tuple[float, float, float, float]
) -> ZoneOccupancy:
    """
    Is this zone clean enough for an owner to render into?

    Measured as local variation rather than raw darkness: a zone can be
    legitimately mid-toned (a coloured panel) and still be clean, whereas
    leftover glyph or rule fragments produce high-frequency detail.

    Scanned as a grid, taking the WORST tile rather than an average. A small
    localised defect is the normal case - case 4's residue is a fragment in
    one corner of its zone - and averaging is precisely how it survived an
    earlier version of this check while being plainly visible.
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

    tile_height = max(region.height // _OCCUPANCY_ROWS, 1)
    tile_width = max(region.width // _OCCUPANCY_COLS, 1)
    worst, worst_box = 0.0, None
    for top in range(0, region.height, tile_height):
        for left in range(0, region.width, tile_width):
            right = min(left + tile_width, region.width)
            bottom = min(top + tile_height, region.height)
            if right - left < 2 or bottom - top < 2:
                continue
            stddev = ImageStat.Stat(region.crop((left, top, right, bottom))).stddev[0]
            if stddev > worst:
                worst, worst_box = stddev, (left, top, right, bottom)

    ink_fraction = min(worst / 128.0, 1.0)
    clean = ink_fraction <= OCCUPANCY_THRESHOLD
    worst_region = None
    if worst_box is not None:
        worst_region = (
            round((box[0] + worst_box[0]) / width, 4),
            round((box[1] + worst_box[1]) / height, 4),
            round((box[0] + worst_box[2]) / width, 4),
            round((box[1] + worst_box[3]) / height, 4),
        )
    return ZoneOccupancy(
        block_id=block_id, bounds=bounds, ink_fraction=round(ink_fraction, 4),
        is_clean=clean, worst_region=worst_region,
        detail=(
            f"worst tile variation {worst:.1f} of 128 "
            f"({'clean' if clean else 'occupied - residue or content present'})"
        ),
    )


class EnforcementResult(BaseModel):
    """What enforcement did, in full, for the manifest."""

    model_config = ConfigDict(extra="forbid")

    render_zones: list[RenderZone] = Field(default_factory=list)
    occupancy: list[ZoneOccupancy] = Field(default_factory=list)
    attempts: list[OwnershipAttempt] = Field(default_factory=list)
    cleanup_actions: list[CleanupAction] = Field(default_factory=list)

    @property
    def unresolved(self) -> list[str]:
        """Blocks that reached the end of the ladder without clean space."""
        resolved = {a.block_id for a in self.attempts if a.succeeded}
        attempted = {a.block_id for a in self.attempts}
        return sorted(attempted - resolved)

    @property
    def known_cost_subtotal(self) -> float:
        """
        What enforcement is KNOWN to have cost. Deliberately not called a
        total: rungs whose cost is unknown are counted separately below.
        """
        return round(sum(a.cost_usd or 0.0 for a in self.attempts), 6)

    @property
    def unknown_cost_attempts(self) -> int:
        return sum(1 for a in self.attempts if a.cost_status == "unknown")


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


def adapt_layout(
    zone: RenderZone, contract: CompositionContract | None
) -> tuple[tuple[float, float, float, float], str] | None:
    """
    Rung 3: move an owner into space the composition says is free.

    Only negative-space zones are candidates, and only ones large enough to
    hold what needs drawing. Relocating into a subject or product zone would
    trade a dirty zone for a covered photograph, which is a worse outcome
    presented as a fix.
    """
    if contract is None:
        return None
    needed_width = zone.bounds[2] - zone.bounds[0]
    needed_height = zone.bounds[3] - zone.bounds[1]
    for candidate in contract.zones_with_role(ZoneRole.NEGATIVE_SPACE):
        width = candidate.bounds[2] - candidate.bounds[0]
        height = candidate.bounds[3] - candidate.bounds[1]
        if width >= needed_width and height >= needed_height:
            relocated = (
                candidate.bounds[0],
                candidate.bounds[1],
                candidate.bounds[0] + needed_width,
                candidate.bounds[1] + needed_height,
            )
            return relocated, (
                f"relocated into the {candidate.zone_id!r} negative-space zone "
                f"({width:.2f}x{height:.2f} available, {needed_width:.2f}x"
                f"{needed_height:.2f} needed)"
            )
    return None


def enforce(
    image_bytes: bytes,
    plan: OwnershipPlan,
    contract: CompositionContract | None = None,
    *,
    allow_reconstruct: bool = True,
) -> tuple[bytes, EnforcementResult]:
    """
    Walk the ladder for every owner zone until it is clean or exhausted.

    Rungs 1-3 are performed; 4 and 5 are recorded rather than performed.
    Regeneration belongs to the generation loop and model lettering is a
    deliberate escalation, not something enforcement should reach for on its
    own. Reaching rung 4 or 5 is recorded honestly so it is visible rather
    than hidden behind a silent cleanup.
    """
    result = EnforcementResult(render_zones=owner_render_zones(plan, contract))
    current = image_bytes

    for zone in result.render_zones:
        occupancy = measure_occupancy(current, zone.block_id, zone.bounds)
        result.occupancy.append(occupancy)

        if occupancy.is_clean:
            result.attempts.append(
                OwnershipAttempt(
                    block_id=zone.block_id, step=LadderStep.REGENERATE, succeeded=True,
                    reason="zone already clean - the model honoured the ownership instruction",
                    input_bounds=zone.bounds,
                    output="image unchanged",
                    validation=f"occupancy {occupancy.ink_fraction:.4f} <= {OCCUPANCY_THRESHOLD}",
                )
            )
            continue

        previous = (
            f"zone occupied (occupancy {occupancy.ink_fraction:.4f} > "
            f"{OCCUPANCY_THRESHOLD}) at {occupancy.worst_region} - {occupancy.detail}"
        )
        result.attempts.append(
            OwnershipAttempt(
                block_id=zone.block_id, step=LadderStep.REGENERATE, succeeded=False,
                reason=previous, input_bounds=zone.bounds,
                output="image unchanged - the model did not leave this zone clean",
                validation=f"occupancy {occupancy.ink_fraction:.4f} > {OCCUPANCY_THRESHOLD}",
            )
        )

        if not allow_reconstruct:
            result.attempts.append(
                OwnershipAttempt(
                    block_id=zone.block_id, step=LadderStep.HUMAN_REVIEW, succeeded=False,
                    reason="reconstruction disabled - escalating rather than rendering over content",
                    previous_failure=previous, input_bounds=zone.bounds,
                    output="none", validation="not attempted",
                )
            )
            continue

        current, detail = reconstruct_zone(current, zone.bounds)
        after = measure_occupancy(current, zone.block_id, zone.bounds)
        result.cleanup_actions.append(
            CleanupAction(
                block_id=zone.block_id, action=str(LadderStep.RECONSTRUCT), bounds=zone.bounds,
                detail=f"{detail}; occupancy {occupancy.ink_fraction:.4f} -> "
                       f"{after.ink_fraction:.4f}",
            )
        )
        result.attempts.append(
            OwnershipAttempt(
                block_id=zone.block_id, step=LadderStep.RECONSTRUCT,
                succeeded=after.is_clean, previous_failure=previous,
                input_bounds=zone.bounds, output=detail,
                reason=(
                    "zone reconstructed and now clean" if after.is_clean
                    else f"reconstruction insufficient - occupancy still {after.ink_fraction:.4f}"
                ),
                validation=(
                    f"re-measured occupancy {after.ink_fraction:.4f} "
                    f"{'<=' if after.is_clean else '>'} {OCCUPANCY_THRESHOLD}"
                ),
                # Local pixel work. Free, and knowably free - which is not the
                # same as a provider call whose price we failed to record.
                provider="local", cost_usd=0.0, cost_status="exact",
            )
        )
        if after.is_clean:
            continue

        relocation = adapt_layout(zone, contract)
        if relocation is not None:
            moved, why = relocation
            relocated_occupancy = measure_occupancy(current, zone.block_id, moved)
            result.cleanup_actions.append(
                CleanupAction(
                    block_id=zone.block_id, action=str(LadderStep.ADAPT_LAYOUT),
                    bounds=moved, detail=why,
                )
            )
            result.attempts.append(
                OwnershipAttempt(
                    block_id=zone.block_id, step=LadderStep.ADAPT_LAYOUT,
                    succeeded=relocated_occupancy.is_clean,
                    reason=why,
                    previous_failure=f"reconstruction left occupancy {after.ink_fraction:.4f}",
                    input_bounds=zone.bounds, output=f"render zone moved to {moved}",
                    validation=(
                        f"destination occupancy {relocated_occupancy.ink_fraction:.4f} "
                        f"{'<=' if relocated_occupancy.is_clean else '>'} {OCCUPANCY_THRESHOLD}"
                    ),
                    provider="local", cost_usd=0.0, cost_status="exact",
                )
            )
            if relocated_occupancy.is_clean:
                continue
            unresolved_after = "relocation found no clean destination"
        else:
            result.attempts.append(
                OwnershipAttempt(
                    block_id=zone.block_id, step=LadderStep.ADAPT_LAYOUT, succeeded=False,
                    reason="no negative-space zone large enough to relocate into",
                    previous_failure=f"reconstruction left occupancy {after.ink_fraction:.4f}",
                    input_bounds=zone.bounds, output="none",
                    validation="the contract declares no suitable destination",
                )
            )
            unresolved_after = "layout adaptation found nowhere to go"

        result.attempts.append(
            OwnershipAttempt(
                block_id=zone.block_id, step=LadderStep.MODEL_LETTERING, succeeded=False,
                reason="not attempted - model lettering is an L3 escalation, not a cleanup",
                previous_failure=unresolved_after,
                input_bounds=zone.bounds, output="none", validation="not attempted",
            )
        )
        result.attempts.append(
            OwnershipAttempt(
                block_id=zone.block_id, step=LadderStep.HUMAN_REVIEW, succeeded=False,
                reason="no rung produced clean space - surfaced rather than rendered over",
                previous_failure="model lettering withheld",
                input_bounds=zone.bounds, output="none",
                validation="escalated for human review",
            )
        )

    return current, result
