"""
Unit tests for SlideImageValidationStage (Phase 8.4 of the Generation ->
Validation proof of loop, see MIGRATION_PLAN.md). No real vision call -
FakeVisionAnalysisProvider throughout.
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.generated_image import GeneratedImage
from app.models.image_validation_result import ImageValidationResult
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.creative_specification_stage import SlideCreativeSpecificationStage
from app.slideshow_stages.image_generation_stage import SlideImageGenerationStage
from app.slideshow_stages.image_validation_stage import SlideImageValidationStage
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import SlideProductLockProfileStage
from tests.fakes import FakeAIProviderRegistry, FakeVisionAnalysisProvider
from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT


def _build_generated_image(db_session, slideshow, monkeypatch) -> GeneratedImage:
    """Runs the full prerequisite chain through a real (fake-backed) GeneratedImage row."""
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )
    SlideProductIsolationStage().run(db_session, slideshow)
    SlideProductLockProfileStage().run(db_session, slideshow)
    SlideCreativeFingerprintStage().run(db_session, slideshow)
    SlideCreativeSpecificationStage().run(db_session, slideshow)
    SlideImageGenerationStage().run(db_session, slideshow)

    slide = slideshow.primary_slide
    return db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()


def test_fails_gracefully_when_the_product_cannot_be_resolved(db_session, slideshow_with_product):
    """A bare GeneratedImage row with no real upstream chain - creative_specification_id points nowhere."""
    result = SlideImageValidationStage().run(
        db_session,
        GeneratedImage(
            slideshow_id=slideshow_with_product.id,
            slide_id=slideshow_with_product.primary_slide.id,
            creative_specification_id="does-not-exist",
            provider="openai",
            model_name="fake",
            prompt_used="fake",
            seed=None,
            generation_time_seconds=0.1,
            file_path="/dev/null",
            analysis_run_id="does-not-exist",
        ),
    )

    assert result.succeeded is False
    assert "Could not resolve the product" in result.error


def test_fails_gracefully_without_any_immutable_profile_fields(db_session, slideshow_with_product, monkeypatch):
    """
    A real GeneratedImage, but the Product's Lock Profile happens to
    populate only contextual-classified vision fields (viewing_angle,
    lighting) - no immutable fields exist to validate against, so the
    stage fails cleanly rather than silently "passing" a check that
    checked nothing.
    """
    contextual_only_lock_profile = {
        "viewing_angle": "eye-level",
        "lighting_characteristics": "soft natural light",
    }
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=contextual_only_lock_profile)),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )
    SlideProductIsolationStage().run(db_session, slideshow_with_product)
    SlideProductLockProfileStage().run(db_session, slideshow_with_product)
    SlideCreativeFingerprintStage().run(db_session, slideshow_with_product)
    SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)
    SlideImageGenerationStage().run(db_session, slideshow_with_product)

    slide = slideshow_with_product.primary_slide
    generated_image = db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()

    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry", FakeAIProviderRegistry()
    )
    result = SlideImageValidationStage().run(db_session, generated_image)

    assert result.succeeded is False
    assert "No immutable Product Profile fields" in result.error


def test_succeeds_all_preserved_passes(db_session, slideshow_with_product, monkeypatch):
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)

    fake_vision = FakeVisionAnalysisProvider(
        result={
            "field_checks": [
                {"field_name": "brand", "preserved": True, "reason": "Brand name matches exactly."},
                {"field_name": "color", "preserved": True, "reason": "Colors match."},
            ],
            "overall_explanation": "All checked characteristics were preserved.",
        }
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = SlideImageValidationStage().run(db_session, generated_image)

    assert result.succeeded is True

    validation = db_session.scalars(
        select(ImageValidationResult).where(
            ImageValidationResult.generated_image_id == generated_image.id,
            ImageValidationResult.is_current.is_(True),
        )
    ).first()
    assert validation is not None
    assert validation.passed is True
    assert validation.overall_explanation == "All checked characteristics were preserved."
    assert len(validation.field_checks_json) == 2

    analysis_run = db_session.get(AnalysisRun, validation.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "image_validation"


def test_one_field_violated_fails_the_whole_validation(db_session, slideshow_with_product, monkeypatch):
    """passed is computed in code from the per-field judgments - never asked of the AI as a bare boolean."""
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)

    fake_vision = FakeVisionAnalysisProvider(
        result={
            "field_checks": [
                {"field_name": "brand", "preserved": True, "reason": "Brand name matches."},
                {
                    "field_name": "color",
                    "preserved": False,
                    "reason": "The generated image shows blue instead of orange.",
                },
            ],
            "overall_explanation": "One characteristic did not match.",
        }
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    SlideImageValidationStage().run(db_session, generated_image)

    validation = db_session.scalars(
        select(ImageValidationResult).where(ImageValidationResult.generated_image_id == generated_image.id)
    ).first()
    assert validation.passed is False
    violated = [c for c in validation.field_checks_json if not c["preserved"]]
    assert len(violated) == 1
    assert "blue instead of orange" in violated[0]["reason"]


def test_fails_gracefully_on_provider_error(db_session, slideshow_with_product, monkeypatch):
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(raise_error=RuntimeError("vision provider down"))
        ),
    )

    result = SlideImageValidationStage().run(db_session, generated_image)

    assert result.succeeded is False
    assert "vision provider down" in result.error
    assert (
        db_session.scalars(
            select(ImageValidationResult).where(
                ImageValidationResult.generated_image_id == generated_image.id
            )
        ).first()
        is None
    )


def test_rerun_produces_new_version_and_flips_previous(db_session, slideshow_with_product, monkeypatch):
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry", FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(
                result={
                    "field_checks": [{"field_name": "brand", "preserved": True, "reason": "ok"}],
                    "overall_explanation": "fine",
                }
            )
        ),
    )

    stage = SlideImageValidationStage()
    stage.run(db_session, generated_image)
    first = db_session.scalars(
        select(ImageValidationResult).where(
            ImageValidationResult.generated_image_id == generated_image.id,
            ImageValidationResult.is_current.is_(True),
        )
    ).first()

    stage.run(db_session, generated_image)
    db_session.refresh(first)
    second = db_session.scalars(
        select(ImageValidationResult).where(
            ImageValidationResult.generated_image_id == generated_image.id,
            ImageValidationResult.is_current.is_(True),
        )
    ).first()

    assert second.id != first.id
    assert first.is_current is False
    assert second.is_current is True
