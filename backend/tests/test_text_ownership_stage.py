"""
Text Ownership Stage (ADR 0001 §4/§6, Package E).

The stage that makes Packages A and C reachable. Before it, "who owns this
block?" could not be answered until the rendering path computed it and threw
it away - which is too late, because the generator has to be told what NOT
to draw BEFORE it draws.
"""

import pytest
from PIL import Image

from app.models.analysis_run import ANALYSIS_TYPE_TEXT_OWNERSHIP, AnalysisRun
from app.models.ocr_result import OCRResult
from app.models.provider_call import ProviderCall
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.composition_contract import record_contract
from app.services.creative_project_profile import apply_user_decisions, record_analysis
from app.services.ownership_artifact import decisions_of, get_current
from app.services.profile_schema import (
    CapabilityLevel,
    FamilyClass,
    OverlayPolicy,
    TextMode,
    TypographySystem,
)
from app.services.text_ownership import ImageStrategy, Owner
from app.slideshow_stages.text_ownership_stage import SlideTextOwnershipStage
from tests.benchmark_loader import load_contract

CASE04_BLOCKS = [
    {"text": "1.", "surface": "overlay",
     "bounding_box": {"x_min": 0.08, "y_min": 0.13, "x_max": 0.18, "y_max": 0.21}},
    {"text": "Your upper back", "surface": "overlay",
     "bounding_box": {"x_min": 0.08, "y_min": 0.26, "x_max": 0.55, "y_max": 0.31}},
    {"text": "pov: this is you #fyp", "surface": "overlay",
     "bounding_box": {"x_min": 0.10, "y_min": 0.70, "x_max": 0.80, "y_max": 0.76}},
]


@pytest.fixture
def analysed(db_session, tmp_path):
    """A slideshow that has been through OCR, the contract stage and the profile."""
    def build(blocks=CASE04_BLOCKS, *, case="case04_posture",
              text_mode=TextMode.DESIGNED_TYPOGRAPHY, typography=None,
              with_contract=True, with_profile=True):
        image_path = tmp_path / "slide.png"
        Image.new("RGB", (64, 64), (240, 240, 240)).save(image_path)

        show = Slideshow()
        db_session.add(show)
        db_session.flush()
        slide = Slide(slideshow_id=show.id, slide_index=0, stored_file_path=str(image_path),
                      original_filename="slide.png", source_type="upload",
                      source_locator="slide.png")
        db_session.add(slide)
        db_session.flush()

        run = AnalysisRun(analysis_type="ocr", provider="fake", model_name="m",
                          status="succeeded", slide_id=slide.id)
        db_session.add(run)
        db_session.flush()

        ocr = OCRResult(analysis_run_id=run.id, slide_id=slide.id,
                        raw_text=" ".join(b["text"] for b in blocks),
                        structured_blocks_json=blocks)
        db_session.add(ocr)
        db_session.flush()
        slide.current_ocr_result_id = ocr.id

        if with_contract:
            record_contract(db_session, slide_id=slide.id, analysis_run_id=run.id,
                            contract=load_contract(case))
        if with_profile:
            record_analysis(db_session, slideshow_id=show.id, analysis_run_id=run.id,
                            primary_text_mode=text_mode, text_mode_confidence=0.9,
                            typography_system=typography)
        db_session.flush()
        db_session.refresh(show)
        return show, slide
    return build


def _decisions(db_session, slide):
    artifact = get_current(db_session, slide.id)
    assert artifact is not None
    return {d.text: d for d in decisions_of(artifact)}


# --------------------------------------------------------------------------
# The chain, end to end and deterministic
# --------------------------------------------------------------------------


def test_ownership_is_persisted_for_every_block(db_session, analysed):
    show, slide = analysed()
    result = SlideTextOwnershipStage().run(db_session, show)

    assert result.succeeded, result.error
    by_text = _decisions(db_session, slide)
    assert set(by_text) == {b["text"] for b in CASE04_BLOCKS}


def test_the_composition_contract_reaches_the_decisions(db_session, analysed):
    """
    Package C's spatial routing, now running as part of analysis rather than
    only in a test. The numeral sits in the contract's `numeral` zone.
    """
    show, slide = analysed()
    SlideTextOwnershipStage().run(db_session, show)

    numeral = _decisions(db_session, slide)["1."]
    assert numeral.composition_zone_id == "numeral"
    assert numeral.owner is Owner.TYPOGRAPHY

    artifact = get_current(db_session, slide.id)
    assert artifact.composition_contract_id is not None
    assert artifact.composition_contract_version is not None


def test_a_platform_caption_is_still_routed_to_the_caption_owner(db_session, analysed):
    show, slide = analysed()
    SlideTextOwnershipStage().run(db_session, show)
    assert _decisions(db_session, slide)["pov: this is you #fyp"].owner is Owner.CAPTION


def test_the_stage_makes_no_provider_call(db_session, analysed):
    """
    Every input already exists by the time this runs. It must not be the
    thing that fails when a provider is down, and it must not appear in a
    ledger that accounts for paid work.
    """
    show, _ = analysed()
    SlideTextOwnershipStage().run(db_session, show)

    run = db_session.query(AnalysisRun).filter(
        AnalysisRun.analysis_type == ANALYSIS_TYPE_TEXT_OWNERSHIP
    ).one()
    assert run.provider == "local"
    assert db_session.query(ProviderCall).filter(
        ProviderCall.analysis_run_id == run.id
    ).count() == 0


# --------------------------------------------------------------------------
# The profile's EFFECTIVE values, not its analysed ones
# --------------------------------------------------------------------------


def test_a_users_overlay_policy_reaches_routing(db_session, analysed):
    """
    Someone who set `remove` has said what should happen to their captions.
    Routing that read the analysed value instead would make the setting
    decorative - it would appear to have been saved and change nothing.
    """
    from app.services.creative_project_profile import get_current_profile

    show, slide = analysed()
    apply_user_decisions(
        db_session, get_current_profile(db_session, show.id),
        overlay_policy=OverlayPolicy.REVIEW_INDIVIDUALLY,
    )
    SlideTextOwnershipStage().run(db_session, show)

    assert _decisions(db_session, slide)["pov: this is you #fyp"].owner is Owner.REVIEW


def test_a_users_text_mode_reaches_routing(db_session, analysed):
    from app.services.creative_project_profile import get_current_profile

    show, slide = analysed()
    apply_user_decisions(
        db_session, get_current_profile(db_session, show.id),
        primary_text_mode=TextMode.PLATFORM_CAPTION,
    )
    SlideTextOwnershipStage().run(db_session, show)

    # "1." fires the standalone-numeral editorial signal, so it stays
    # designed typography - a project default does not override a block that
    # has spoken for itself.
    assert _decisions(db_session, slide)["1."].owner is Owner.TYPOGRAPHY


# --------------------------------------------------------------------------
# Capability level reaching Owner - the gap the A-D report recorded
# --------------------------------------------------------------------------


def _system(level):
    return TypographySystem(primary_family_class=FamilyClass.SERIF, capability_level=level)


def test_l1_typography_goes_to_the_deterministic_renderer(db_session, analysed):
    show, slide = analysed(typography=_system(CapabilityLevel.L1))
    SlideTextOwnershipStage().run(db_session, show)
    assert _decisions(db_session, slide)["Your upper back"].owner is Owner.TYPOGRAPHY


@pytest.mark.parametrize("level", [CapabilityLevel.L2, CapabilityLevel.L3])
def test_typography_beyond_the_renderer_is_left_to_the_image(db_session, analysed, level):
    """
    The genuine gap the Packages A-D report recorded: benchmark 5's treatment
    is annotated designed typography but integrated into the artwork, so an
    L1 renderer would draw it flat. Flat type where the source had it
    occluded or wrapped is worse than letting the model attempt it.
    """
    show, slide = analysed(typography=_system(level))
    SlideTextOwnershipStage().run(db_session, show)

    decision = _decisions(db_session, slide)["Your upper back"]
    assert decision.owner is Owner.IMAGE
    assert decision.image_strategy is ImageStrategy.GENERATED
    assert any("renderer is L1" in reason for reason in decision.evidence)


def test_capability_never_overrides_a_caption(db_session, analysed):
    """The gate is about what the TYPE renderer can draw. A caption is the
    user's, and its routing is not a capability question."""
    show, slide = analysed(typography=_system(CapabilityLevel.L3))
    SlideTextOwnershipStage().run(db_session, show)
    assert _decisions(db_session, slide)["pov: this is you #fyp"].owner is Owner.CAPTION


# --------------------------------------------------------------------------
# Degradation
# --------------------------------------------------------------------------


def test_without_a_contract_it_still_produces_ownership(db_session, analysed):
    """
    A contract stage that failed must not take ownership down with it -
    routing falls back to wording, which is worse but not wrong.
    """
    show, slide = analysed(with_contract=False)
    result = SlideTextOwnershipStage().run(db_session, show)

    assert result.succeeded, result.error
    by_text = _decisions(db_session, slide)
    assert len(by_text) == len(CASE04_BLOCKS)
    assert all(d.composition_zone_id is None for d in by_text.values())
    assert get_current(db_session, slide.id).composition_contract_id is None


def test_without_a_profile_it_still_produces_ownership(db_session, analysed):
    show, slide = analysed(with_profile=False)
    result = SlideTextOwnershipStage().run(db_session, show)
    assert result.succeeded, result.error
    assert len(_decisions(db_session, slide)) == len(CASE04_BLOCKS)


def test_a_slide_with_no_text_records_an_empty_plan_not_nothing(db_session, analysed):
    """
    An absent artifact and an artifact saying "no text here" are different
    facts, and only one of them is a finding.
    """
    show, slide = analysed(blocks=[])
    result = SlideTextOwnershipStage().run(db_session, show)

    assert result.succeeded, result.error
    artifact = get_current(db_session, slide.id)
    assert artifact is not None
    assert decisions_of(artifact) == []


def test_re_running_supersedes_rather_than_duplicating(db_session, analysed):
    show, slide = analysed()
    SlideTextOwnershipStage().run(db_session, show)
    first = get_current(db_session, slide.id)

    SlideTextOwnershipStage().run(db_session, show)
    second = get_current(db_session, slide.id)

    assert second.id != first.id
    db_session.refresh(first)
    assert not first.is_current
