"""
Unit tests for Bundle Composition (Phase 10.7 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §12's
"Bundle Composition" addendum) - the Generation Engine and Quality
Engine sides. No real provider call - Fakes throughout, same discipline
as test_generation_engine.py, whose `_build_full_prerequisites` helper
this file reuses for the slide's own (first) member product.
"""

from sqlalchemy import select

from app.ai_providers.base import GeneratedImageResult
from app.models.bundle_composition import BundleComposition, BundleCompositionMember
from app.models.creative_specification import CreativeSpecification
from app.models.product import Product
from app.models.product_reference_image import ProductReferenceImage
from app.services.decision_engine import decide_generation_plan
from app.services.generation_engine import GenerationAttemptResult, run_bundle_generation_attempt
from app.services.quality_engine import assess_bundle_candidate
from app.slideshow_stages.base import StageResult
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider, FakeVisionAnalysisProvider
from tests.test_slide_image_generation_stage import _build_full_prerequisites

_IDENTITY_PASSES = {"field_checks": [{"field_name": "silhouette", "preserved": True, "reason": "Matches."}]}
_IDENTITY_FAILS = {"field_checks": [{"field_name": "silhouette", "preserved": False, "reason": "Wrong shape."}]}


def _get_creative_specification(db_session, slideshow):
    return db_session.get(
        CreativeSpecification, slideshow.primary_slide.current_creative_specification_id
    )


def _make_second_product_with_library(db_session, tmp_path, *, name="Red Mug") -> Product:
    """
    A real file on disk, not just a DB row - run_bundle_member_identity_validation
    (unlike the plain generation-engine tests above) actually reads
    reference image bytes from disk, since it calls a real vision
    provider interface even though that provider itself is faked.
    """
    product = Product(display_name=name)
    db_session.add(product)
    db_session.flush()
    real_file = tmp_path / f"{product.id}_ref.jpg"
    real_file.write_bytes(b"\x89PNG\r\n\x1a\nfake-reference-bytes")
    db_session.add(
        ProductReferenceImage(
            product_id=product.id,
            file_path=str(real_file),
            isolation_method="user_upload",
            role="front",
            library_status="included",
            quality_score=0.9,
        )
    )
    db_session.commit()
    return product


def _bundle_members(product_a_id, product_b_id):
    return [
        {"product_id": product_a_id, "role_in_scene": "hero perfume bottle"},
        {"product_id": product_b_id, "role_in_scene": "background mug"},
    ]


def test_run_bundle_generation_attempt_creates_composition_and_members(
    db_session, slideshow_with_product, monkeypatch, tmp_path
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    second_product = _make_second_product_with_library(db_session, tmp_path)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    first_product_id = slide.current_product_appearances[0].product_id
    plan = decide_generation_plan(
        "fast", bundle_members=_bundle_members(first_product_id, second_product.id)
    )

    result = run_bundle_generation_attempt(db_session, slide, creative_specification, plan)

    assert isinstance(result, GenerationAttemptResult)
    assert len(result.candidates) == 1
    assert result.attempt.bundle_composition_id is not None
    assert result.attempt.generation_reference_set_id is None
    assert all(c.generation_reference_set_id is None for c in result.candidates)

    bundle_composition = db_session.get(BundleComposition, result.attempt.bundle_composition_id)
    assert bundle_composition is not None
    members = list(
        db_session.scalars(
            select(BundleCompositionMember).where(
                BundleCompositionMember.bundle_composition_id == bundle_composition.id
            ).order_by(BundleCompositionMember.rank)
        )
    )
    assert [m.product_id for m in members] == [first_product_id, second_product.id]
    assert [m.role_in_scene for m in members] == ["hero perfume bottle", "background mug"]
    assert all(m.generation_reference_set_id is not None for m in members)


def test_bundle_prompt_includes_every_member_role(db_session, slideshow_with_product, monkeypatch, tmp_path):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    second_product = _make_second_product_with_library(db_session, tmp_path)
    fake_image_provider = FakeImageGenerationProvider()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=fake_image_provider),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    first_product_id = slide.current_product_appearances[0].product_id
    plan = decide_generation_plan(
        "fast", bundle_members=_bundle_members(first_product_id, second_product.id)
    )

    run_bundle_generation_attempt(db_session, slide, creative_specification, plan)

    intent = fake_image_provider.last_request.creative_intent
    assert "hero perfume bottle" in intent
    assert "background mug" in intent
    assert "BUNDLE" in intent


def test_bundle_reference_paths_are_every_members_paths_concatenated(
    db_session, slideshow_with_product, monkeypatch, tmp_path
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    second_product = _make_second_product_with_library(db_session, tmp_path)
    fake_image_provider = FakeImageGenerationProvider()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=fake_image_provider),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    first_product_id = slide.current_product_appearances[0].product_id
    plan = decide_generation_plan(
        "fast", bundle_members=_bundle_members(first_product_id, second_product.id)
    )

    run_bundle_generation_attempt(db_session, slide, creative_specification, plan)

    paths = fake_image_provider.last_request.reference_image_paths
    assert any(second_product.id in p for p in paths)
    assert len(paths) >= 2


def test_fails_cleanly_when_a_member_product_does_not_exist(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    first_product_id = slide.current_product_appearances[0].product_id
    plan = decide_generation_plan("fast", bundle_members=_bundle_members(first_product_id, "does-not-exist"))

    result = run_bundle_generation_attempt(db_session, slide, creative_specification, plan)

    assert isinstance(result, StageResult)
    assert result.succeeded is False


def test_fails_cleanly_when_a_member_has_no_library(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    empty_product = Product(display_name="No Library Product")
    db_session.add(empty_product)
    db_session.commit()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    first_product_id = slide.current_product_appearances[0].product_id
    plan = decide_generation_plan("fast", bundle_members=_bundle_members(first_product_id, empty_product.id))

    result = run_bundle_generation_attempt(db_session, slide, creative_specification, plan)

    assert isinstance(result, StageResult)
    assert "No Generation Reference Set available" in result.error


def test_requires_at_least_one_bundle_member(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("fast", bundle_members=[])

    result = run_bundle_generation_attempt(db_session, slide, creative_specification, plan)

    assert isinstance(result, StageResult)
    assert result.succeeded is False


# --- assess_bundle_candidate (Quality Engine) -------------------------


def _run_bundle_attempt(db_session, slideshow_with_product, monkeypatch, tmp_path, image_result=None):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    second_product = _make_second_product_with_library(db_session, tmp_path)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider(result=image_result)),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    first_product_id = slide.current_product_appearances[0].product_id
    plan = decide_generation_plan(
        "fast", bundle_members=_bundle_members(first_product_id, second_product.id)
    )
    result = run_bundle_generation_attempt(db_session, slide, creative_specification, plan)
    return result.candidates[0], first_product_id, second_product.id


def _fake_png_result():
    return GeneratedImageResult(
        image_bytes=b"\x89PNG\r\n\x1a\nfake-bytes",
        provider="openai",
        model="fake-image-model",
        prompt_used="prompt",
        seed=None,
        generation_time_seconds=0.1,
    )


def test_assess_bundle_candidate_accepts_when_every_member_passes_identity(
    db_session, slideshow_with_product, monkeypatch, tmp_path
):
    candidate, product_a, product_b = _run_bundle_attempt(
        db_session, slideshow_with_product, monkeypatch, tmp_path, image_result=_fake_png_result()
    )
    real_file = tmp_path / "candidate.png"
    real_file.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")
    candidate.file_path = str(real_file)
    db_session.commit()

    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(results_by_schema_name={"identity_validation": _IDENTITY_PASSES})
        ),
    )
    _PHOTOREALISM_PASSES = {
        "realistic_lighting": True, "believable_shadows": True, "material_accuracy": True,
        "reflections_correct": True, "texture_quality": "excellent", "perspective_correct": True,
        "object_integrity": True, "human_anatomy": "not_applicable", "ai_artefacts_detected": False,
        "image_sharpness": "excellent", "reasons": ["clean"],
    }
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(results_by_schema_name={"photorealism": _PHOTOREALISM_PASSES})
        ),
    )

    assessment = assess_bundle_candidate(db_session, candidate)

    assert assessment.accepted is True
    assert assessment.image_validation_result_id is None
    assert len(assessment.image_validation_result_ids_json) == 2


def test_assess_bundle_candidate_rejects_when_any_member_fails_identity(
    db_session, slideshow_with_product, monkeypatch, tmp_path
):
    candidate, product_a, product_b = _run_bundle_attempt(
        db_session, slideshow_with_product, monkeypatch, tmp_path, image_result=_fake_png_result()
    )
    real_file = tmp_path / "candidate.png"
    real_file.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")
    candidate.file_path = str(real_file)
    db_session.commit()

    class _AlternatingVisionProvider:
        model = "fake-vision-model"
        provider = "openai"

        def __init__(self):
            self.calls = 0

        def analyze_creative(self, image_bytes, prompt_spec, response_schema):
            self.calls += 1
            return _IDENTITY_PASSES if self.calls == 1 else _IDENTITY_FAILS

    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=_AlternatingVisionProvider()),
    )

    assessment = assess_bundle_candidate(db_session, candidate)

    assert assessment.accepted is False
    assert assessment.overall_confidence_score == 0.0
    # Photorealism must never be spent - the floor didn't clear for every member.
    assert assessment.photorealism_json is None


def test_assess_bundle_candidate_rejects_a_candidate_with_no_bundle_composition(
    db_session, slideshow_with_product, monkeypatch
):
    """Guard: assess_bundle_candidate refuses a plain single-product candidate, not silently misbehave."""
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )
    from app.services.generation_engine import run_generation_attempt

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("fast")
    result = run_generation_attempt(db_session, slide, creative_specification, plan)

    outcome = assess_bundle_candidate(db_session, result.candidates[0])

    assert isinstance(outcome, StageResult)
    assert outcome.succeeded is False
