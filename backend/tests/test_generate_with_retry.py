"""
Unit tests for the basic automatic retry loop (Phase 10.2 of AI
Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §14; Photorealism dimension added Phase 10.3). No real
provider calls - Fake providers throughout.
"""

from sqlalchemy import select

from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.services.generate_with_retry import RetryLoopResult, generate_with_retry
from app.slideshow_stages.base import StageResult
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider, FakeVisionAnalysisProvider
from tests.test_slide_image_generation_stage import _build_full_prerequisites

_IDENTITY_PASSES = {"field_checks": [{"field_name": "silhouette", "preserved": True, "reason": "Matches."}]}
_CREATIVE_PASSES = {
    "field_checks": [{"field_name": "color", "preserved": True, "reason": "Matches."}],
    "overall_explanation": "Everything preserved.",
}
_CREATIVE_FAILS = {
    "field_checks": [{"field_name": "color", "preserved": False, "reason": "Wrong shade."}],
    "overall_explanation": "Color mismatch.",
}
_PHOTOREALISM_PASSES = {
    "realistic_lighting": True,
    "believable_shadows": True,
    "material_accuracy": True,
    "reflections_correct": True,
    "texture_quality": "excellent",
    "perspective_correct": True,
    "object_integrity": True,
    "human_anatomy": "not_applicable",
    "ai_artefacts_detected": False,
    "image_sharpness": "excellent",
    "reasons": ["clean, photorealistic render"],
}


def _patch_generation(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )


def _patch_validation(monkeypatch, *, creative_result):
    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": creative_result,
            "photorealism": _PHOTOREALISM_PASSES,
        }
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )


def test_accepts_on_the_first_attempt_when_a_candidate_passes(
    db_session, slideshow_with_product, monkeypatch
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)
    _patch_validation(monkeypatch, creative_result=_CREATIVE_PASSES)

    result = generate_with_retry(db_session, slideshow_with_product, "fast")

    assert isinstance(result, RetryLoopResult)
    assert len(result.attempts) == 1
    assert result.winner is not None
    assert result.winner.quality_assessment.accepted is True

    slide = slideshow_with_product.primary_slide
    current = db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()
    assert current is not None
    assert current.id == result.winner.generated_image.id


def test_retries_once_then_accepts_when_the_second_attempt_passes(
    db_session, slideshow_with_product, monkeypatch
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)

    call_count = {"n": 0}

    class _AlternatingVisionProvider:
        model = "fake-vision-model"
        provider = "openai"

        def analyze_creative(self, image_bytes, prompt_spec, response_schema):
            schema_name = prompt_spec.get("schema_name")
            if schema_name == "identity_validation":
                return _IDENTITY_PASSES
            if schema_name == "photorealism":
                return _PHOTOREALISM_PASSES
            call_count["n"] += 1
            # First attempt's one "fast"-mode candidate fails creative
            # validation; the retry's candidate passes.
            return _CREATIVE_FAILS if call_count["n"] == 1 else _CREATIVE_PASSES

    alternating_provider = _AlternatingVisionProvider()
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=alternating_provider),
    )
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=alternating_provider),
    )

    result = generate_with_retry(db_session, slideshow_with_product, "fast", max_retries=1)

    assert isinstance(result, RetryLoopResult)
    assert len(result.attempts) == 2
    assert result.attempts[1].attempt.retry_of_generation_attempt_id == result.attempts[0].attempt.id
    assert result.winner is not None
    assert result.winner.generated_image.generation_attempt_id == result.attempts[1].attempt.id


def test_exhausting_retries_returns_no_winner_without_error(
    db_session, slideshow_with_product, monkeypatch
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)
    _patch_validation(monkeypatch, creative_result=_CREATIVE_FAILS)

    result = generate_with_retry(db_session, slideshow_with_product, "fast", max_retries=1)

    assert isinstance(result, RetryLoopResult)
    assert len(result.attempts) == 2  # the original attempt + 1 retry, then stop
    assert result.winner is None

    slide = slideshow_with_product.primary_slide
    assert (
        db_session.scalars(
            select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
        ).first()
        is None
    )


def test_fails_cleanly_without_a_creative_specification(db_session, slideshow_with_slide, monkeypatch):
    _patch_generation(monkeypatch)

    result = generate_with_retry(db_session, slideshow_with_slide, "fast")

    assert isinstance(result, StageResult)
    assert result.succeeded is False
    assert "No Creative Specification" in result.error


def test_fails_cleanly_and_stops_immediately_without_a_library(
    db_session, slideshow_with_product, monkeypatch
):
    """A missing Library fails identically on every retry - stop after the first attempt, don't burn the budget."""
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch, with_library=False)
    _patch_generation(monkeypatch)

    result = generate_with_retry(db_session, slideshow_with_product, "fast", max_retries=2)

    assert isinstance(result, StageResult)
    assert "No Generation Reference Set available" in result.error
    assert db_session.scalars(select(GenerationAttempt)).first() is None
