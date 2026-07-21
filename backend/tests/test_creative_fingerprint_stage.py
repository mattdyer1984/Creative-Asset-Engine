"""
Unit tests for CreativeFingerprintStage (plan §13's Stage contract tests).
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.models.creative_fingerprint import CreativeFingerprint
from app.stages.creative_fingerprint_stage import CreativeFingerprintStage
from app.stages.ocr_stage import OCRStage
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


def test_succeeds_and_updates_blueprint(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )

    stage = CreativeFingerprintStage()
    result = stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    assert result.succeeded is True

    db_session.refresh(creative_with_blueprint.blueprint)
    fingerprint_id = creative_with_blueprint.blueprint.current_creative_fingerprint_id
    assert fingerprint_id is not None

    fingerprint = db_session.get(CreativeFingerprint, fingerprint_id)
    assert fingerprint.is_current is True
    structured = fingerprint.structured_json
    assert structured["target_audience"] == "health-conscious young adults"

    analysis_run = db_session.get(AnalysisRun, fingerprint.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "creative_fingerprint"


def test_incorporates_ocr_text_as_context_when_available(db_session, creative_with_blueprint, monkeypatch):
    """Directly verifies the OCR text is actually included in the prompt sent to the provider."""
    monkeypatch.setattr(
        "app.stages.ocr_stage.default_registry", FakeAIProviderRegistry()
    )
    OCRStage().run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    fake_vision = FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    CreativeFingerprintStage().run(
        db_session, creative_with_blueprint, creative_with_blueprint.blueprint
    )

    assert fake_vision.last_prompt_spec is not None
    assert "Fresh Squeezed. Zero Sugar Added." in fake_vision.last_prompt_spec["prompt"]


def test_proceeds_without_ocr_text_if_none_exists_yet(db_session, creative_with_blueprint, monkeypatch):
    """No OCR has run yet - the stage should still succeed, just without that context."""
    fake_vision = FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = CreativeFingerprintStage().run(
        db_session, creative_with_blueprint, creative_with_blueprint.blueprint
    )

    assert result.succeeded is True
    assert "OCR" not in fake_vision.last_prompt_spec["prompt"]


def test_fails_gracefully_on_provider_error(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(raise_error=RuntimeError("provider timed out"))
        ),
    )

    result = CreativeFingerprintStage().run(
        db_session, creative_with_blueprint, creative_with_blueprint.blueprint
    )

    assert result.succeeded is False
    assert "provider timed out" in result.error

    db_session.refresh(creative_with_blueprint.blueprint)
    assert creative_with_blueprint.blueprint.current_creative_fingerprint_id is None

    run = db_session.scalars(select(AnalysisRun)).first()
    assert run.status == STATUS_FAILED


def test_rerun_produces_new_version(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )

    stage = CreativeFingerprintStage()
    stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)
    db_session.refresh(creative_with_blueprint.blueprint)
    first_id = creative_with_blueprint.blueprint.current_creative_fingerprint_id

    stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)
    db_session.refresh(creative_with_blueprint.blueprint)
    second_id = creative_with_blueprint.blueprint.current_creative_fingerprint_id

    assert second_id != first_id
    first = db_session.get(CreativeFingerprint, first_id)
    assert first.is_current is False
