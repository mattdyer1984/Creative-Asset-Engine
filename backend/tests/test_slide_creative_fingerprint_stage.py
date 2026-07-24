"""
Unit tests for SlideCreativeFingerprintStage (new pipeline, Phase 2.4c) -
mirrors tests/test_creative_fingerprint_stage.py's coverage.

FINGERPRINT_RESULT is defined here (not imported from the old test file)
so this file stays self-contained for when Phase 2.7 removes the old
pipeline's test files - later new-pipeline tests (Phase 2.4e's
recreation prompt tests) import it from here instead.
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.models.creative_fingerprint import CreativeFingerprint
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.ocr_stage import SlideOCRStage
from tests.fakes import FakeAIProviderRegistry, FakeVisionAnalysisProvider

FINGERPRINT_RESULT = {
    "visual_style": "clean, minimalist product photography",
    "marketing_objective": "drive trial purchase",
    "emotional_appeal": ["freshness", "health"],
    "target_audience": "health-conscious young adults",
    "color_palette": ["orange", "white", "green"],
    "typography_style": "bold sans-serif",
    "layout_and_composition": "centered product shot with clean background",
    "background_environment": "plain studio backdrop",
    "lighting_style": "soft, even studio lighting",
    "graphic_style": "photographic, minimal graphic overlay",
    "product_prominence": "product fills most of the frame",
    "marketing_angle": "natural, no added sugar",
    "visual_hierarchy": "product first, then wordmark, then tagline",
    "trust_elements": ["no added sugar callout"],
    "promotional_devices": ["limited time offer badge"],
    "extensions": "",
}


def test_succeeds_and_updates_slide(db_session, slideshow_with_slide, monkeypatch):
    fake_registry = FakeAIProviderRegistry(
        vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry", fake_registry
    )

    stage = SlideCreativeFingerprintStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is True
    # Real-world-driven cost/quality change (see MIGRATION_PLAN.md).
    assert fake_registry.vision_calls == ["gemini"]

    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    fingerprint_id = slide.current_creative_fingerprint_id
    assert fingerprint_id is not None

    fingerprint = db_session.get(CreativeFingerprint, fingerprint_id)
    assert fingerprint.is_current is True
    assert fingerprint.slide_id == slide.id
    structured = fingerprint.structured_json
    assert structured["target_audience"] == "health-conscious young adults"

    analysis_run = db_session.get(AnalysisRun, fingerprint.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "creative_fingerprint"
    assert analysis_run.slide_id == slide.id


def test_incorporates_ocr_text_as_context_when_available(db_session, slideshow_with_slide, monkeypatch):
    """Directly verifies the OCR text is actually included in the prompt sent to the provider."""
    monkeypatch.setattr(
        "app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry()
    )
    SlideOCRStage().run(db_session, slideshow_with_slide)
    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    ocr_result_id = slide.current_ocr_result_id

    fake_vision = FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    SlideCreativeFingerprintStage().run(db_session, slideshow_with_slide)

    assert fake_vision.last_prompt_spec is not None
    assert "Fresh Squeezed. Zero Sugar Added." in fake_vision.last_prompt_spec["prompt"]

    db_session.refresh(slide)
    fingerprint = db_session.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
    # Phase 7.4 (Narrative pass, see MIGRATION_PLAN.md): records exactly
    # which OCR result was actually incorporated.
    assert fingerprint.ocr_result_id == ocr_result_id


def test_proceeds_without_ocr_text_if_none_exists_yet(db_session, slideshow_with_slide, monkeypatch):
    """No OCR has run yet - the stage should still succeed, just without that context."""
    fake_vision = FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = SlideCreativeFingerprintStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is True
    assert "OCR" not in fake_vision.last_prompt_spec["prompt"]

    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    fingerprint = db_session.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
    assert fingerprint.ocr_result_id is None


def test_fails_gracefully_on_provider_error(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(raise_error=RuntimeError("provider timed out"))
        ),
    )

    result = SlideCreativeFingerprintStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "provider timed out" in result.error

    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    assert slide.current_creative_fingerprint_id is None

    run = db_session.scalars(select(AnalysisRun)).first()
    assert run.status == STATUS_FAILED


def test_rerun_produces_new_version(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )

    stage = SlideCreativeFingerprintStage()
    stage.run(db_session, slideshow_with_slide)
    slide = slideshow_with_slide.primary_slide
    db_session.refresh(slide)
    first_id = slide.current_creative_fingerprint_id

    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slide)
    second_id = slide.current_creative_fingerprint_id

    assert second_id != first_id
    first = db_session.get(CreativeFingerprint, first_id)
    assert first.is_current is False
