"""
Creative Project Profile Stage (ADR 0001 §14, Package E).

WP-1.1 built the profile and guaranteed that re-analysis never discards a
human decision. Nothing wrote to it, so that guarantee had never actually
been exercised by a writer. It is now.
"""

import pytest
from PIL import Image

from app.models.analysis_run import ANALYSIS_TYPE_CREATIVE_PROFILE, AnalysisRun
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.ocr_result import OCRResult
from app.models.provider_call import ProviderCall
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.creative_project_profile import (
    apply_user_decisions,
    effective_overlay_policy,
    effective_primary_text_mode,
    effective_typography_system,
    get_current_profile,
)
from app.services.profile_schema import (
    CapabilityLevel,
    FamilyClass,
    OverlayPolicy,
    TextMode,
)
from app.services.source_style import RenderingFamily
from app.slideshow_stages.creative_profile_stage import (
    SlideshowCreativeProfileStage,
    build_typography_system,
    infer_text_mode,
)

DESIGNED = [
    {"text": "Your upper back", "surface": "overlay"},
    {"text": "feels rounded", "surface": "overlay"},
]
CAPTIONS = [
    {"text": "pov: you finally found the one #fyp", "surface": "overlay"},
    {"text": "no because why is this so good 😭", "surface": "overlay"},
]
PACKAGING = [
    {"text": "HIGH PROTEIN", "surface": "physical"},
    {"text": "500g", "surface": "physical"},
]


# --------------------------------------------------------------------------
# Text mode: deterministic, and it must not need a provider
# --------------------------------------------------------------------------


def test_caption_blocks_make_it_a_caption_project():
    mode, confidence, evidence = infer_text_mode([CAPTIONS], RenderingFamily.PHOTOGRAPHIC)
    assert mode is TextMode.PLATFORM_CAPTION
    assert confidence > 0.5
    assert evidence.blocks and evidence.project_mode_reasons


def test_designed_blocks_make_it_a_designed_project():
    mode, _, _ = infer_text_mode([DESIGNED], RenderingFamily.ILLUSTRATED)
    assert mode is TextMode.DESIGNED_TYPOGRAPHY


def test_packaging_text_does_not_get_a_vote():
    """
    Product-native text appears in both kinds of project, so it says nothing
    about which this is. Counting it would let a slideshow full of packaging
    outvote the one designed headline that actually decides the question.
    """
    with_packaging = infer_text_mode([DESIGNED + PACKAGING * 10], None)
    without = infer_text_mode([DESIGNED], None)
    assert with_packaging[0] is without[0] is TextMode.DESIGNED_TYPOGRAPHY
    assert with_packaging[1] == without[1]


def test_a_disagreeing_project_records_the_default_but_not_the_confidence():
    """
    A near-even split is still routed - a default beats nothing - but it must
    not be presented as a finding, or a coin flip becomes evidence.
    """
    mode, confidence, evidence = infer_text_mode([DESIGNED + CAPTIONS], None)
    assert mode in (TextMode.DESIGNED_TYPOGRAPHY, TextMode.PLATFORM_CAPTION)
    assert confidence <= 0.6
    assert any("not as a confident finding" in r for r in evidence.project_mode_reasons)


def test_no_deciding_text_falls_back_to_style_and_says_so():
    mode, confidence, evidence = infer_text_mode([PACKAGING], RenderingFamily.ILLUSTRATED)
    assert mode is TextMode.DESIGNED_TYPOGRAPHY
    assert confidence < 0.5, "a style-only guess must not read as a confident answer"
    assert any("no deciding text" in r for r in evidence.project_mode_reasons)


def test_with_no_evidence_at_all_the_answer_is_low_confidence():
    mode, confidence, _ = infer_text_mode([[]], None)
    assert mode is TextMode.PLATFORM_CAPTION
    assert confidence < 0.3


def test_the_blocks_outvote_the_style():
    """
    Style breaks ties; it does not decide. An illustrated creative can carry
    platform captions, and the text is the better evidence when it speaks.
    """
    mode, _, evidence = infer_text_mode([CAPTIONS], RenderingFamily.ILLUSTRATED)
    assert mode is TextMode.PLATFORM_CAPTION
    assert any("the blocks win" in r for r in evidence.project_mode_reasons)


def test_every_block_appears_in_the_evidence():
    """A decision a reviewer cannot audit is not reviewable."""
    _, _, evidence = infer_text_mode([DESIGNED, CAPTIONS], None)
    assert len(evidence.blocks) == len(DESIGNED) + len(CAPTIONS)


# --------------------------------------------------------------------------
# Typography system from a provider response
# --------------------------------------------------------------------------


def _typography_response(**overrides):
    base = {
        "primary_family_class": "serif",
        "secondary_family_class": None,
        "capability_level": "L1",
        "colour_roles": {"accent": "dark-red", "body": "near-black"},
        "text_roles": {
            "headline": {"family_class": "serif", "weight": "regular",
                         "colour_role": "body", "size_ratio": 2.9},
            "bullet": {"family_class": "serif", "weight": "regular",
                       "colour_role": "accent", "size_ratio": 1.0},
        },
        "size_scale": {"headline_to_body": 2.9},
    }
    base.update(overrides)
    return base


def test_a_well_formed_typography_response_becomes_a_system():
    system = build_typography_system(_typography_response())
    assert system.primary_family_class is FamilyClass.SERIF
    assert system.capability_level is CapabilityLevel.L1
    assert system.colour_roles["accent"] == "dark-red"
    assert system.text_roles["headline"].size_ratio == 2.9


def test_an_unknown_capability_level_is_treated_as_l3_not_l1():
    """
    L1 is the optimistic answer and the dangerous default: claiming it for
    integrated typography produces a flat, wrong recreation. An unreadable
    answer must route AWAY from the deterministic renderer, not into it.
    """
    system = build_typography_system(_typography_response(capability_level="probably fine"))
    assert system.capability_level is CapabilityLevel.L3


def test_one_unusable_role_does_not_lose_the_others():
    response = _typography_response()
    response["text_roles"]["broken"] = {"family_class": "comic sans", "weight": "regular",
                                        "colour_role": "body", "size_ratio": 1.0}
    system = build_typography_system(response)
    assert "broken" not in system.text_roles
    assert {"headline", "bullet"} <= set(system.text_roles)


def test_an_unrecognised_family_falls_back_rather_than_crashing():
    system = build_typography_system(_typography_response(primary_family_class="handwriting"))
    assert system.primary_family_class is FamilyClass.GROTESQUE


# --------------------------------------------------------------------------
# The stage
# --------------------------------------------------------------------------


class _FakeVision:
    provider = "fake"
    model = "fake-vision"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def analyze_creative(self, *, image_bytes, prompt_spec, response_schema, usage_sink):
        self.calls += 1
        usage_sink.update({"prompt_tokens": 11, "completion_tokens": 22})
        return self.response


@pytest.fixture
def slideshow_factory(db_session, tmp_path):
    def build(blocks, fingerprint=None):
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

        if fingerprint is not None:
            print_row = CreativeFingerprint(analysis_run_id=run.id, slide_id=slide.id,
                                            structured_json=fingerprint)
            db_session.add(print_row)
            db_session.flush()
            slide.current_creative_fingerprint_id = print_row.id

        db_session.flush()
        db_session.refresh(show)
        return show
    return build


def _run(monkeypatch, db_session, show, response=None):
    fake = _FakeVision(response or _typography_response())
    monkeypatch.setattr(
        "app.slideshow_stages.creative_profile_stage.default_registry.vision", lambda: fake
    )
    return SlideshowCreativeProfileStage().run(db_session, show), fake


def test_a_designed_project_gets_a_typography_system(
    monkeypatch, db_session, slideshow_factory
):
    show = slideshow_factory(DESIGNED, {"visual_style": "flat vector illustration"})
    result, fake = _run(monkeypatch, db_session, show)

    assert result.succeeded, result.error
    assert fake.calls == 1

    profile = get_current_profile(db_session, show.id)
    assert effective_primary_text_mode(profile) is TextMode.DESIGNED_TYPOGRAPHY
    system = effective_typography_system(profile)
    assert system is not None
    assert system.primary_family_class is FamilyClass.SERIF


def test_a_caption_project_costs_nothing(monkeypatch, db_session, slideshow_factory):
    """
    A UGC caption project has no design typography to read. Paying a vision
    call to be told so is waste, and the benchmark fixtures assert the same
    thing (`typography_system: null` for every ugc_photographic case).
    """
    show = slideshow_factory(CAPTIONS, {"visual_style": "handheld phone photo"})
    result, fake = _run(monkeypatch, db_session, show)

    assert result.succeeded, result.error
    assert fake.calls == 0

    profile = get_current_profile(db_session, show.id)
    assert effective_primary_text_mode(profile) is TextMode.PLATFORM_CAPTION
    assert effective_typography_system(profile) is None


def test_a_call_that_never_happened_is_not_in_the_ledger(
    monkeypatch, db_session, slideshow_factory
):
    """
    Cost reporting reads ProviderCall exclusively. A zero-cost row for
    deterministic work would put a call in the ledger that never occurred -
    the opposite of what that ledger is for.
    """
    show = slideshow_factory(CAPTIONS)
    _run(monkeypatch, db_session, show)

    run = db_session.query(AnalysisRun).filter(
        AnalysisRun.analysis_type == ANALYSIS_TYPE_CREATIVE_PROFILE
    ).one()
    assert db_session.query(ProviderCall).filter(
        ProviderCall.analysis_run_id == run.id
    ).count() == 0


def test_a_paid_call_is_in_the_ledger_with_its_prompt(
    monkeypatch, db_session, slideshow_factory
):
    show = slideshow_factory(DESIGNED)
    _run(monkeypatch, db_session, show)

    run = db_session.query(AnalysisRun).filter(
        AnalysisRun.analysis_type == ANALYSIS_TYPE_CREATIVE_PROFILE
    ).one()
    call = db_session.query(ProviderCall).filter(
        ProviderCall.analysis_run_id == run.id
    ).one()
    assert call.prompt_id == "analysis.typography_system"
    assert call.prompt_tokens == 11 and call.completion_tokens == 22


def test_re_analysis_never_discards_a_user_decision(
    monkeypatch, db_session, slideshow_factory
):
    """
    WP-1.1's central guarantee, exercised by a real writer for the first
    time. Someone who chose `remove` must not find `keep` restored because
    the slideshow was analysed again.
    """
    show = slideshow_factory(DESIGNED)
    _run(monkeypatch, db_session, show)

    profile = get_current_profile(db_session, show.id)
    apply_user_decisions(
        db_session, profile,
        primary_text_mode=TextMode.PLATFORM_CAPTION,
        overlay_policy=OverlayPolicy.REMOVE,
    )

    _run(monkeypatch, db_session, show)

    fresh = get_current_profile(db_session, show.id)
    assert fresh.id != profile.id, "re-analysis supersedes rather than updating"
    assert effective_overlay_policy(fresh) is OverlayPolicy.REMOVE
    assert effective_primary_text_mode(fresh) is TextMode.PLATFORM_CAPTION
    assert fresh.analysed_primary_text_mode == str(TextMode.DESIGNED_TYPOGRAPHY), (
        "the analyser's own view is still recorded alongside the user's"
    )


def test_a_provider_failure_leaves_no_half_written_profile(
    monkeypatch, db_session, slideshow_factory
):
    show = slideshow_factory(DESIGNED)

    class _Broken(_FakeVision):
        def analyze_creative(self, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "app.slideshow_stages.creative_profile_stage.default_registry.vision",
        lambda: _Broken(None),
    )
    result = SlideshowCreativeProfileStage().run(db_session, show)
    assert not result.succeeded
    assert get_current_profile(db_session, show.id) is None


def test_the_evidence_is_persisted_for_review(monkeypatch, db_session, slideshow_factory):
    show = slideshow_factory(DESIGNED)
    _run(monkeypatch, db_session, show)
    profile = get_current_profile(db_session, show.id)
    evidence = profile.classification_evidence_json
    assert evidence["blocks"], "per-block working must survive to the database"
    assert evidence["project_mode_reasons"]
