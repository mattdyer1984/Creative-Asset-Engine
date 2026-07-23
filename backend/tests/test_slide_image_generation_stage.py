"""
Unit tests for SlideImageGenerationStage (Phase 8.3 of the Generation ->
Validation proof of loop, see MIGRATION_PLAN.md). No real OpenAI call -
FakeImageGenerationProvider throughout, matching this codebase's
established discipline for every AI-backed stage test.
"""

from pathlib import Path

from sqlalchemy import select

from app.ai_providers.base import GeneratedImageResult
from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.generated_image import GeneratedImage
from app.models.product_reference_image import ProductReferenceImage
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.creative_specification_stage import SlideCreativeSpecificationStage
from app.slideshow_stages.image_generation_stage import SlideImageGenerationStage
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import SlideProductLockProfileStage
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider, FakeVisionAnalysisProvider
from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT


def _build_full_prerequisites(db_session, slideshow, monkeypatch, *, with_library=True):
    """
    Runs every stage Image Generation depends on: Isolation, Lock
    Profile, Fingerprint, Creative Specification. Phase 9.3 of Product
    Lock v2 (see MIGRATION_PLAN.md) adds a fifth prerequisite -
    Reference Selection needs at least one Library-included
    ProductReferenceImage, so `with_library=True` (the default) marks
    every row Product Isolation just cropped as included, directly
    (not by re-running Reference Scoring's own AI call here - that
    Stage has its own dedicated test file, this one just needs a
    populated Library to select from).
    """
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
    SlideProductIsolationStage().run(db_session, slideshow)
    SlideProductLockProfileStage().run(db_session, slideshow)
    SlideCreativeFingerprintStage().run(db_session, slideshow)
    SlideCreativeSpecificationStage().run(db_session, slideshow)

    if with_library:
        current_reference_images = db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.is_current.is_(True))
        ).all()
        for reference_image in current_reference_images:
            reference_image.library_status = "included"
            reference_image.role = "front"
            reference_image.quality_score = 0.8
        db_session.commit()


def test_fails_gracefully_without_a_creative_specification(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )

    result = SlideImageGenerationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No Creative Specification" in result.error
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_fails_gracefully_without_a_product_assigned(db_session, slideshow_with_slide, monkeypatch):
    """slideshow_with_slide has no product assigned at all - a different gap than a missing spec."""
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )

    result = SlideImageGenerationStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "No Creative Specification" in result.error


def test_succeeds_and_persists_generated_image(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)

    fake_image_provider = FakeImageGenerationProvider(
        result=GeneratedImageResult(
            image_bytes=b"\x89PNG\r\n\x1a\nreal-fake-bytes",
            provider="openai",
            model="fake-image-model",
            prompt_used="compiled prompt text",
            seed=None,
            generation_time_seconds=1.23,
        )
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry",
        FakeAIProviderRegistry(image_generation_provider=fake_image_provider),
    )

    result = SlideImageGenerationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is True

    slide = slideshow_with_product.primary_slide
    generated = db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()
    assert generated is not None
    assert generated.slideshow_id == slideshow_with_product.id
    assert generated.provider == "openai"
    assert generated.model_name == "fake-image-model"
    assert generated.prompt_used == "compiled prompt text"
    assert generated.seed is None
    assert generated.generation_time_seconds == 1.23
    assert Path(generated.file_path).exists()
    assert Path(generated.file_path).read_bytes() == b"\x89PNG\r\n\x1a\nreal-fake-bytes"
    assert generated.generation_reference_set_id is not None

    analysis_run = db_session.get(AnalysisRun, generated.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "generated_image"
    assert analysis_run.slide_id == slide.id

    from app.models.generation_reference_set import GenerationReferenceSet

    generation_reference_set = db_session.get(
        GenerationReferenceSet, generated.generation_reference_set_id
    )
    assert generation_reference_set.generated_image_id == generated.id


def test_generation_request_is_built_from_real_specification_and_reference_images(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Phase 9.3 of Product Lock v2 (see MIGRATION_PLAN.md) - the compiled
    request must carry the selected reference image paths and the
    scene fields, and must NOT describe the product in text (the
    Creative Specification's fake "subject" text, e.g. "orange juice",
    must never appear - that's the whole point of the reference-image
    rewrite, reference images are the only source of product identity
    now).
    """
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)

    fake_image_provider = FakeImageGenerationProvider()
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry",
        FakeAIProviderRegistry(image_generation_provider=fake_image_provider),
    )

    SlideImageGenerationStage().run(db_session, slideshow_with_product)

    assert fake_image_provider.last_request is not None
    assert "orange juice" not in fake_image_provider.last_request.creative_intent.lower()
    assert len(fake_image_provider.last_request.reference_image_paths) >= 1


def test_fails_gracefully_without_a_library(db_session, slideshow_with_product, monkeypatch):
    """
    Reference Scoring never ran (or found nothing worth including) -
    Reference Selection returns None, and the Stage must fail cleanly
    rather than compile a product-blind, text-only request.
    """
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch, with_library=False)

    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )

    result = SlideImageGenerationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No Generation Reference Set available" in result.error
    slide = slideshow_with_product.primary_slide
    assert (
        db_session.scalars(select(GeneratedImage).where(GeneratedImage.slide_id == slide.id)).first()
        is None
    )


def test_fails_gracefully_on_provider_error(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry",
        FakeAIProviderRegistry(
            image_generation_provider=FakeImageGenerationProvider(
                raise_error=RuntimeError("image provider down")
            )
        ),
    )

    result = SlideImageGenerationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "image provider down" in result.error

    slide = slideshow_with_product.primary_slide
    assert (
        db_session.scalars(
            select(GeneratedImage).where(GeneratedImage.slide_id == slide.id)
        ).first()
        is None
    )


def test_rerun_produces_new_version_and_flips_previous(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideImageGenerationStage()
    stage.run(db_session, slideshow_with_product)
    slide = slideshow_with_product.primary_slide
    first = db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()

    stage.run(db_session, slideshow_with_product)
    db_session.refresh(first)
    second = db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()

    assert second.id != first.id
    assert first.is_current is False
    assert second.is_current is True
