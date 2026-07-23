"""
Unit tests for SlideImageValidationStage (Phase 8.4 of the Generation ->
Validation proof of loop; extended in Phase 9.4 of Product Lock v2 with
Stage 1 Identity Validation, see MIGRATION_PLAN.md). No real vision
call - FakeVisionAnalysisProvider throughout.
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.generated_image import GeneratedImage
from app.models.image_validation_result import ImageValidationResult
from app.models.product_reference_image import ProductReferenceImage
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.creative_specification_stage import SlideCreativeSpecificationStage
from app.slideshow_stages.image_generation_stage import SlideImageGenerationStage
from app.slideshow_stages.image_validation_stage import SlideImageValidationStage, _build_prompt
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import SlideProductLockProfileStage
from tests.fakes import FakeAIProviderRegistry, FakeVisionAnalysisProvider
from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT

# A passing Stage 1 result - every test that wants Stage 2 to actually
# run (Phase 9.4) needs this, since _build_generated_image now always
# produces a GeneratedImage with a real generation_reference_set_id
# (Phase 9.3), so Stage 1 always runs first.
_IDENTITY_PASSES = {
    "field_checks": [
        {"field_name": "silhouette", "preserved": True, "reason": "Matches reference."},
        {"field_name": "color", "preserved": True, "reason": "Matches reference."},
    ],
}

_IDENTITY_FAILS = {
    "field_checks": [
        {"field_name": "silhouette", "preserved": False, "reason": "Wrong bottle shape entirely."},
    ],
}


def _mark_current_reference_images_included(db_session):
    """
    Phase 9.3 of Product Lock v2 (see MIGRATION_PLAN.md) - Image
    Generation now requires a populated Canonical Reference Library
    (Reference Selection's precondition). Sets library_status directly
    rather than re-running Reference Scoring's own AI call here - that
    Stage has its own dedicated test file.
    """
    current_reference_images = db_session.scalars(
        select(ProductReferenceImage).where(ProductReferenceImage.is_current.is_(True))
    ).all()
    for reference_image in current_reference_images:
        reference_image.library_status = "included"
        reference_image.role = "front"
        reference_image.quality_score = 0.8
    db_session.commit()


def test_build_prompt_asks_for_the_short_field_name_only():
    """
    Real gap found live-verifying Phase 8.5 (see MIGRATION_PLAN.md): the
    first prompt wording let the model return "brand: Bella Vita Luxury"
    as field_name instead of just "brand", making the UI's field labels
    unusably verbose. The fix is prompt wording, not schema - guard that
    the prompt clearly separates field_name from its expected value.
    """
    prompt = _build_prompt([("brand", "Sunrise"), ("color", "orange (#FFA500)")])

    assert 'field_name "brand": expected value = Sunrise' in prompt
    assert 'field_name "color": expected value = orange (#FFA500)' in prompt
    assert "ONLY the short field_name" in prompt


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
    _mark_current_reference_images_included(db_session)
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
    checked nothing. Identity Validation (Stage 1) still runs first and
    must pass for Stage 2 to even be reached.
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
    _mark_current_reference_images_included(db_session)
    SlideProductLockProfileStage().run(db_session, slideshow_with_product)
    SlideCreativeFingerprintStage().run(db_session, slideshow_with_product)
    SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)
    SlideImageGenerationStage().run(db_session, slideshow_with_product)

    slide = slideshow_with_product.primary_slide
    generated_image = db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()

    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(
                results_by_schema_name={"identity_validation": _IDENTITY_PASSES}
            )
        ),
    )
    result = SlideImageValidationStage().run(db_session, generated_image)

    assert result.succeeded is False
    assert "No immutable Product Profile fields" in result.error


def test_succeeds_all_preserved_passes(db_session, slideshow_with_product, monkeypatch):
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)

    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": {
                "field_checks": [
                    {"field_name": "brand", "preserved": True, "reason": "Brand name matches exactly."},
                    {"field_name": "color", "preserved": True, "reason": "Colors match."},
                ],
                "overall_explanation": "All checked characteristics were preserved.",
            },
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
    assert validation.identity_passed is True
    assert len(validation.identity_checks_json) == 2

    analysis_run = db_session.get(AnalysisRun, validation.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "image_validation"


def test_one_field_violated_fails_the_whole_validation(db_session, slideshow_with_product, monkeypatch):
    """passed is computed in code from the per-field judgments - never asked of the AI as a bare boolean."""
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)

    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": {
                "field_checks": [
                    {"field_name": "brand", "preserved": True, "reason": "Brand name matches."},
                    {
                        "field_name": "color",
                        "preserved": False,
                        "reason": "The generated image shows blue instead of orange.",
                    },
                ],
                "overall_explanation": "One characteristic did not match.",
            },
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


def test_identity_failure_short_circuits_before_stage_2(db_session, slideshow_with_product, monkeypatch):
    """
    Stage 1 fails -> passed=False immediately, Stage 2 never runs (no
    field_checks_json entries, no Product Profile lookup needed) - the
    ADR's explicit cost-saving short-circuit design (§7).
    """
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)

    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={"identity_validation": _IDENTITY_FAILS}
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = SlideImageValidationStage().run(db_session, generated_image)

    assert result.succeeded is True  # the STAGE succeeded at determining a real failure

    validation = db_session.scalars(
        select(ImageValidationResult).where(ImageValidationResult.generated_image_id == generated_image.id)
    ).first()
    assert validation.passed is False
    assert validation.identity_passed is False
    assert validation.identity_checks_json == _IDENTITY_FAILS["field_checks"]
    assert validation.field_checks_json == []  # Stage 2 never ran
    assert "Identity validation failed" in validation.overall_explanation


def test_passed_requires_both_identity_and_creative_to_pass(db_session, slideshow_with_product, monkeypatch):
    """identity_passed=True but creative fails -> overall passed is still False (the AND rule, ADR §1)."""
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)

    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": {
                "field_checks": [{"field_name": "brand", "preserved": False, "reason": "Wrong brand text."}],
                "overall_explanation": "Brand text does not match.",
            },
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
    assert validation.identity_passed is True
    assert validation.passed is False  # identity True AND creative False -> overall False


def test_no_reference_set_skips_identity_and_stage_2_runs_as_before(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Tri-state (ADR §7): a GeneratedImage with no generation_reference_set_id
    (every row created before this ADR shipped) skips Stage 1 entirely -
    identity_passed/identity_checks_json stay null, not False, and
    `passed` is Stage 2's result alone, exactly as it worked before
    Phase 9.4.
    """
    generated_image = _build_generated_image(db_session, slideshow_with_product, monkeypatch)
    generated_image.generation_reference_set_id = None
    db_session.commit()

    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "image_validation": {
                "field_checks": [{"field_name": "brand", "preserved": True, "reason": "Matches."}],
                "overall_explanation": "All good.",
            }
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
    assert validation.identity_passed is None
    assert validation.identity_checks_json is None
    assert validation.passed is True
    assert len(validation.field_checks_json) == 1


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
                results_by_schema_name={
                    "identity_validation": _IDENTITY_PASSES,
                    "image_validation": {
                        "field_checks": [{"field_name": "brand", "preserved": True, "reason": "ok"}],
                        "overall_explanation": "fine",
                    },
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
