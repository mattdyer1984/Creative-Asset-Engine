"""
The live rendering gate (ADR 0001, Package E5).

Everything Packages A-E built, exercised as one chain on a real benchmark
image: analysis decides ownership, enforcement clears the zones, the L1
renderer draws, and the manifest accounts for every block.

Deliberately run against `case04_posture`, the case the whole programme has
used as its hardest evidence - it has a numeral, a two-weight headline,
bullets with coloured markers, a rule that OCR cannot see, and a residue that
an earlier detector called clean.
"""

import pathlib

import pytest
from PIL import Image

from app.models.analysis_run import AnalysisRun
from app.models.ocr_result import OCRResult
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.composition_contract import contract_of, get_current_contract, record_contract
from app.services.creative_project_profile import (
    effective_typography_system,
    get_current_profile,
    record_analysis,
)
from app.services.graphic_ownership import OCCUPANCY_THRESHOLD, measure_occupancy
from app.services.ownership_artifact import decisions_of, get_current
from app.services.profile_schema import (
    CapabilityLevel,
    FamilyClass,
    MarkerRole,
    RuleRole,
    TextMode,
    TextRole,
    TypographySystem,
)
from app.services.text_ownership import Owner, OwnershipPlan, assert_single_ownership
from app.services.typography import font_availability
from app.services.typography_pipeline import apply_typography
from app.slideshow_stages.text_ownership_stage import SlideTextOwnershipStage
from tests.benchmark_loader import load_contract

CASE04 = pathlib.Path(__file__).parent / "benchmarks" / "case04_posture"

# Positions measured from original.jpg, so the contract's zones and these
# blocks describe the same picture. A test that invented positions would
# prove the plumbing and nothing about the case.
CASE04_BLOCKS = [
    {"text": "1.", "surface": "overlay",
     "bounding_box": {"x_min": 0.079, "y_min": 0.120, "x_max": 0.186, "y_max": 0.220}},
    {"text": "Your upper back", "surface": "overlay",
     "bounding_box": {"x_min": 0.079, "y_min": 0.254, "x_max": 0.600, "y_max": 0.310}},
    {"text": "feels rounded", "surface": "overlay",
     "bounding_box": {"x_min": 0.079, "y_min": 0.312, "x_max": 0.540, "y_max": 0.366}},
    {"text": "You struggle to straighten up", "surface": "overlay",
     "bounding_box": {"x_min": 0.079, "y_min": 0.410, "x_max": 0.335, "y_max": 0.480}},
    {"text": "Shoulders keep falling forward", "surface": "overlay",
     "bounding_box": {"x_min": 0.079, "y_min": 0.515, "x_max": 0.335, "y_max": 0.580}},
]

CASE04_SYSTEM = TypographySystem(
    primary_family_class=FamilyClass.SERIF,
    capability_level=CapabilityLevel.L1,
    colour_roles={"body": "near-black", "accent": "dark-red"},
    text_roles={
        "numeral": TextRole(family_class=FamilyClass.SERIF, weight="regular",
                            colour_role="accent", size_ratio=2.6),
        "headline": TextRole(family_class=FamilyClass.SERIF, weight="regular",
                             colour_role="body", size_ratio=1.9),
        "accent": TextRole(family_class=FamilyClass.SERIF, weight="regular", italic=True,
                           colour_role="accent", size_ratio=1.9),
        "body": TextRole(family_class=FamilyClass.SERIF, weight="regular",
                         colour_role="body", size_ratio=1.0),
    },
    # Case 4's rule under the numeral and its red bullet markers. Both are
    # part of the type system and neither appears in OCR - the rule carries
    # no text at all, and the markers are colour, not wording.
    rule_roles={"numeral": RuleRole(colour_role="accent", width_ratio=0.62,
                                    thickness_ratio=0.035, gap_ratio=0.06)},
    marker_roles={"body": MarkerRole(glyph="\u2022", colour_role="accent")},
    size_scale={"headline_to_body": 1.9},
)

fonts_available = pytest.mark.skipif(
    not all(font_availability().values()),
    reason="logical font tokens unresolved on this host - see docs/FONT_PORTABILITY.md",
)


@pytest.fixture
def analysed_case04(db_session, tmp_path):
    """A slide carrying case 4's real image and its full analysis chain."""
    image_path = tmp_path / "case04.png"
    with Image.open(CASE04 / "original.jpg") as source:
        source.convert("RGB").save(image_path)

    show = Slideshow()
    db_session.add(show)
    db_session.flush()
    slide = Slide(slideshow_id=show.id, slide_index=0, stored_file_path=str(image_path),
                  original_filename="case04.png", source_type="upload",
                  source_locator="case04.png")
    db_session.add(slide)
    db_session.flush()

    run = AnalysisRun(analysis_type="ocr", provider="fake", model_name="m",
                      status="succeeded", slide_id=slide.id)
    db_session.add(run)
    db_session.flush()

    ocr = OCRResult(analysis_run_id=run.id, slide_id=slide.id,
                    raw_text=" ".join(b["text"] for b in CASE04_BLOCKS),
                    structured_blocks_json=CASE04_BLOCKS)
    db_session.add(ocr)
    db_session.flush()
    slide.current_ocr_result_id = ocr.id

    record_contract(db_session, slide_id=slide.id, analysis_run_id=run.id,
                    contract=load_contract("case04_posture"))
    record_analysis(db_session, slideshow_id=show.id, analysis_run_id=run.id,
                    primary_text_mode=TextMode.DESIGNED_TYPOGRAPHY,
                    text_mode_confidence=0.95, typography_system=CASE04_SYSTEM)
    db_session.flush()
    db_session.refresh(show)
    return show, slide


def _render(db_session, show, slide):
    """Analysis, then rendering, reading only what analysis persisted."""
    assert SlideTextOwnershipStage().run(db_session, show).succeeded

    artifact = get_current(db_session, slide.id)
    profile = get_current_profile(db_session, show.id)
    plan = OwnershipPlan(decisions=decisions_of(artifact))

    source_bytes = pathlib.Path(slide.stored_file_path).read_bytes()
    roles = {"block-0": "numeral", "block-1": "headline",
             "block-2": "accent", "block-3": "body", "block-4": "body"}
    return plan, apply_typography(
        source_bytes, plan, effective_typography_system(profile),
        role_for_block=roles,
        profile_id=profile.id,
        contract=contract_of(get_current_contract(db_session, slide.id)),
        effective_policies={"text_mode": "designed_typography"},
    )


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@fonts_available
def test_case04_runs_the_whole_chain_and_accounts_for_every_block(
    db_session, analysed_case04
):
    """
    The gate. Ownership comes from the persisted artifact, zones from the
    persisted contract, type from the persisted profile - nothing re-derived
    at render time, so the manifest describes work that actually happened.
    """
    show, slide = analysed_case04
    plan, (rendered, manifest) = _render(db_session, show, slide)

    assert rendered, "the renderer produced no image"
    assert manifest.accounts_for_every_block(), (
        f"blocks vanished: rendered={[b.block_id for b in manifest.rendered_blocks]} "
        f"skipped={[b.block_id for b in manifest.skipped_blocks]}"
    )
    assert len(manifest.rendered_blocks) == len(CASE04_BLOCKS)
    assert not manifest.warnings, manifest.warnings


@fonts_available
def test_the_manifest_pins_what_it_used_rather_than_resolving_it_later(
    db_session, analysed_case04
):
    """
    ADR: a project re-analysed next week must not rewrite the explanation of
    an image produced today. That requires ids and concrete faces recorded at
    render time, not references resolved on read.
    """
    show, slide = analysed_case04
    _, (_, manifest) = _render(db_session, show, slide)

    assert manifest.profile_id == get_current_profile(db_session, show.id).id
    assert manifest.typography_schema_version
    assert manifest.font_token_bindings
    for token, binding in manifest.font_token_bindings.items():
        assert binding, f"{token} was recorded without the face it resolved to"


@fonts_available
def test_the_rule_zone_is_enforced_even_though_no_block_mentions_it(
    db_session, analysed_case04
):
    """
    Package D through the live path. Nothing in the OCR output refers to the
    rule under the numeral; only the Composition Contract declares it, and
    only because it does is space reserved and measured.
    """
    show, slide = analysed_case04
    _, (_, manifest) = _render(db_session, show, slide)

    rule = next((z for z in manifest.render_zones if z.zone_id == "numeral-rule"), None)
    assert rule is not None, "the contract-declared rule zone was not enforced"
    assert "no text block" in rule.source
    assert any(o.block_id == "zone:numeral-rule" for o in manifest.zone_occupancy)


@fonts_available
def test_every_ladder_attempt_is_auditable(db_session, analysed_case04):
    show, slide = analysed_case04
    _, (_, manifest) = _render(db_session, show, slide)

    assert manifest.ownership_attempts
    for attempt in manifest.ownership_attempts:
        assert attempt.input_bounds is not None
        assert attempt.output and attempt.validation
        assert attempt.cost_status in {"no_provider_call", "exact", "estimated", "unknown"}


@fonts_available
def test_enforcement_clears_the_zones_it_reports_dirty(db_session, analysed_case04):
    """
    The original still carries its own text, so the renderer's zones start
    occupied. A pass that reported them dirty and drew anyway would stack new
    type on old - the defect enforcement exists to prevent.
    """
    show, slide = analysed_case04
    _, (rendered, manifest) = _render(db_session, show, slide)

    cleaned = [a for a in manifest.ownership_attempts
               if a.step == "reconstruct" and a.succeeded]
    assert cleaned, "the original's own text should have needed clearing"
    for action in manifest.cleanup_actions:
        assert "->" in action.detail


def test_ownership_holds_before_anything_is_drawn(db_session, analysed_case04):
    """
    Runs without fonts: the ownership half of the gate must be checkable on
    a host that cannot render, or a font-less CI box would skip the invariant
    that matters most.
    """
    show, slide = analysed_case04
    assert SlideTextOwnershipStage().run(db_session, show).succeeded

    plan = OwnershipPlan(decisions=decisions_of(get_current(db_session, slide.id)))
    assert_single_ownership(plan)
    assert len(plan.decisions) == len(CASE04_BLOCKS)
    assert all(d.owner is Owner.TYPOGRAPHY for d in plan.decisions), (
        "case 4 is entirely designed typography"
    )
    assert plan.texts_the_model_must_not_render(), (
        "the generator must be told what a renderer will place"
    )


@fonts_available
def test_the_rendered_output_is_a_real_image_not_the_source(db_session, analysed_case04):
    show, slide = analysed_case04
    source = pathlib.Path(slide.stored_file_path).read_bytes()
    _, (rendered, _) = _render(db_session, show, slide)

    assert rendered != source
    with Image.open(pathlib.Path(slide.stored_file_path)) as original:
        import io
        with Image.open(io.BytesIO(rendered)) as result:
            assert result.size == original.size, "rendering must not resize the creative"


@fonts_available
def test_the_headline_zone_ends_clean_enough_to_have_been_redrawn(
    db_session, analysed_case04
):
    """
    A weak but real end-to-end signal: after enforcement and rendering, the
    headline zone still carries ink - if it were empty, the renderer had
    cleared the space and then failed to draw into it, which would pass every
    structural assertion above while producing a blank column.
    """
    show, slide = analysed_case04
    _, (rendered, _) = _render(db_session, show, slide)

    contract = load_contract("case04_posture")
    headline = next(z for z in contract.zones if z.zone_id == "headline")
    after = measure_occupancy(rendered, "headline", headline.bounds)
    assert after.ink_fraction > OCCUPANCY_THRESHOLD, (
        "the headline zone is empty - space was cleared but nothing was drawn"
    )


# --------------------------------------------------------------------------
# Legibility. Every assertion above passed on an unusable image.
# --------------------------------------------------------------------------
#
# The first run of this gate produced text at 124px in an 81px box: it wrapped
# to three lines, overflowed into the bullets below, and the whole column was
# illegible overlapping type. Every structural check still passed, because the
# blocks HAD been rendered and the manifest DID account for them.
#
# A gate that passes on an image nobody could ship is not a gate. These check
# the two things the eye catches instantly and the structure cannot see.


def _ink_rows(image_bytes, bounds, threshold=120):
    """Rows within `bounds` that carry dark pixels, as image-normalised y."""
    import io

    with Image.open(io.BytesIO(image_bytes)) as source:
        grey = source.convert("L")
        width, height = grey.size
        px = grey.load()
        x0, y0, x1, y1 = (int(bounds[0] * width), int(bounds[1] * height),
                          int(bounds[2] * width), int(bounds[3] * height))
        rows = set()
        for y in range(max(y0, 0), min(y1, height)):
            if any(px[x, y] < threshold for x in range(max(x0, 0), min(x1, width))):
                rows.add(round(y / height, 4))
        return rows


@fonts_available
def test_no_block_is_drawn_outside_its_own_zone(db_session, analysed_case04):
    """
    Type must fit the space it was given. Overflow is not a cosmetic problem:
    it lands on the neighbouring block and destroys both.
    """
    show, slide = analysed_case04
    _, (rendered, manifest) = _render(db_session, show, slide)

    for block in manifest.rendered_blocks:
        x0, y0, x1, y1 = block.bounds
        # A generous band below the zone. Anything drawn here came from this
        # block overflowing, since enforcement cleared the space first.
        below = (x0, y1 + 0.005, x1, min(y1 + (y1 - y0), 1.0))
        neighbours = [
            b for b in manifest.rendered_blocks
            if b.block_id != block.block_id and b.bounds[1] < below[3] and b.bounds[3] > below[1]
        ]
        if neighbours:
            continue  # another block legitimately owns that space
        assert not _ink_rows(rendered, below), (
            f"{block.block_id} ({block.text[:30]!r}) overflowed below its zone"
        )


@fonts_available
def test_the_accent_role_is_actually_drawn_in_its_accent_colour(
    db_session, analysed_case04
):
    """
    Benchmark 4's accent is dark red. It was being drawn near-black, because
    the style's colour ROLE (`accent`) was handed straight to a function that
    only knows named colours - and the schema-level tests all passed, since
    they only checked the accent role DIFFERED from the body role. It did.
    Both were still drawn in the same colour.
    """
    import io

    show, slide = analysed_case04
    _, (rendered, _) = _render(db_session, show, slide)

    with Image.open(io.BytesIO(rendered)) as image:
        px = image.convert("RGB").load()
        width, height = image.size

        def red_pixels(bounds):
            x0, y0, x1, y1 = bounds
            return sum(
                1
                for x in range(int(x0 * width), int(x1 * width))
                for y in range(int(y0 * height), int(y1 * height))
                if px[x, y][0] - max(px[x, y][1], px[x, y][2]) > 40
            )

        # "feels rounded" is the accent line; "Your upper back" is body colour.
        accent = next(b for b in manifest_blocks(db_session, show, slide)
                      if b.role == "accent")
        headline = next(b for b in manifest_blocks(db_session, show, slide)
                        if b.role == "headline")
        assert red_pixels(accent.bounds) > 200, "the accent line is not red"
        assert red_pixels(headline.bounds) == 0, "the headline should not be red"


def manifest_blocks(db_session, show, slide):
    _, (_, manifest) = _render(db_session, show, slide)
    return manifest.rendered_blocks


@fonts_available
def test_an_unresolvable_colour_role_is_reported_not_silently_blackened(
    db_session, analysed_case04
):
    """
    The fallback still exists - a crashed render is worse than a wrong
    colour - but it must never be silent, which is what let the flattening
    above survive.
    """
    show, slide = analysed_case04
    profile = get_current_profile(db_session, show.id)
    broken = CASE04_SYSTEM.model_copy(update={"colour_roles": {"body": "near-black"}})
    profile.analysed_typography_system_json = broken.model_dump(mode="json")
    db_session.flush()

    _, (_, manifest) = _render(db_session, show, slide)
    assert any("accent" in w and "flatten" in w for w in manifest.warnings), manifest.warnings


@fonts_available
def test_a_graphic_zone_nobody_will_redraw_is_left_alone(db_session, analysed_case04):
    """
    Clearing a zone no owner will draw into does not clean it - it DELETES
    the element. The first live run proved it: enforcement reconstructed the
    rule under the numeral away, no rule role existed to put it back, and the
    finished image had simply lost a piece of the design while every
    structural check passed.
    """
    show, slide = analysed_case04
    profile = get_current_profile(db_session, show.id)
    without_rule = CASE04_SYSTEM.model_copy(update={"rule_roles": {}, "divider_roles": {}})
    profile.analysed_typography_system_json = without_rule.model_dump(mode="json")
    db_session.flush()

    _, (rendered, manifest) = _render(db_session, show, slide)

    assert not any(z.zone_id == "numeral-rule" for z in manifest.render_zones), (
        "an unowned graphic zone must not be enforced"
    )
    assert any("numeral-rule" in w for w in manifest.warnings), manifest.warnings

    # And the original element survives untouched.
    contract = load_contract("case04_posture")
    rule = next(z for z in contract.zones if z.zone_id == "numeral-rule")
    assert not measure_occupancy(rendered, "numeral-rule", rule.bounds).is_clean


@fonts_available
def test_the_rule_is_redrawn_when_the_system_owns_it(db_session, analysed_case04):
    """The other half: with a rule role, the zone is cleared AND redrawn."""
    show, slide = analysed_case04
    _, (rendered, manifest) = _render(db_session, show, slide)

    assert any(z.zone_id == "numeral-rule" for z in manifest.render_zones)
    contract = load_contract("case04_posture")
    rule = next(z for z in contract.zones if z.zone_id == "numeral-rule")
    after = measure_occupancy(rendered, "numeral-rule", rule.bounds)
    assert not after.is_clean, "the rule zone was cleared and never redrawn"
