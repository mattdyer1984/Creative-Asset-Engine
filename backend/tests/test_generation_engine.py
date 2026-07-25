"""
Unit tests for the Generation Engine (Phase 10.2 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §12).
No real provider call - FakeImageGenerationProvider throughout, same
discipline as test_slide_image_generation_stage.py, whose
`_build_full_prerequisites` helper this file reuses rather than
duplicating (product + Library + Creative Specification setup is
identical - Phase 10.2 extends the same single-call machinery, not a
parallel one).
"""

from sqlalchemy import select

from app.ai_providers.base import GeneratedImageResult
from app.models.creative_specification import CreativeSpecification
from app.models.generation_attempt import GenerationAttempt
from app.models.scene_analysis import SceneAnalysis
from app.services.decision_engine import decide_generation_plan
from app.services.generation_engine import GenerationAttemptResult, run_generation_attempt
from app.slideshow_stages.base import StageResult
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider
from tests.test_slide_image_generation_stage import _build_full_prerequisites


def _get_creative_specification(db_session, slideshow):
    return db_session.get(
        CreativeSpecification, slideshow.primary_slide.current_creative_specification_id
    )


def test_generates_exactly_candidate_count_candidates(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("balanced")  # candidate_count == 3

    result = run_generation_attempt(db_session, slide, creative_specification, plan)

    assert isinstance(result, GenerationAttemptResult)
    assert len(result.candidates) == 3
    assert [c.candidate_index for c in result.candidates] == [0, 1, 2]
    assert all(c.generation_attempt_id == result.attempt.id for c in result.candidates)
    assert all(c.is_current is False for c in result.candidates)  # not "current" until Quality picks a winner


def test_every_candidate_shares_the_same_reference_set(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("balanced")

    result = run_generation_attempt(db_session, slide, creative_specification, plan)

    reference_set_ids = {c.generation_reference_set_id for c in result.candidates}
    assert reference_set_ids == {result.attempt.generation_reference_set_id}
    assert None not in reference_set_ids


def test_attempt_persists_the_decision_plan(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("fast")

    result = run_generation_attempt(db_session, slide, creative_specification, plan)

    stored = db_session.get(GenerationAttempt, result.attempt.id)
    assert stored.quality_mode == "fast"
    assert stored.decision_json["candidate_count"] == 1
    assert stored.retry_of_generation_attempt_id is None


def test_fails_cleanly_without_a_library(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch, with_library=False)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("fast")

    result = run_generation_attempt(db_session, slide, creative_specification, plan)

    assert isinstance(result, StageResult)
    assert result.succeeded is False
    assert "No Generation Reference Set available" in result.error
    assert db_session.scalars(select(GenerationAttempt)).first() is None


def test_one_candidate_failing_does_not_stop_the_others(db_session, slideshow_with_product, monkeypatch):
    """A provider error on one candidate call shouldn't lose the attempt's other, successful candidates."""
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)

    class _FlakyProvider:
        model = "fake-image-model"
        provider = "openai"

        def __init__(self):
            self.calls = 0

        def generate_image(self, request):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("provider hiccup")
            return GeneratedImageResult(
                image_bytes=b"\x89PNG\r\n\x1a\nfake-bytes",
                provider="openai",
                model="fake-image-model",
                prompt_used="prompt",
                seed=None,
                generation_time_seconds=0.5,
            )

        @property
        def capabilities(self):
            from app.ai_providers.base import ProviderCapabilities

            return ProviderCapabilities(
                supports_reference_images=True,
                max_reference_images=16,
                supports_masking=True,
                supports_inpainting=True,
                supported_resolutions=["1024x1024"],
            )

    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=_FlakyProvider()),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("balanced")  # candidate_count == 3

    result = run_generation_attempt(db_session, slide, creative_specification, plan)

    assert isinstance(result, GenerationAttemptResult)
    assert len(result.candidates) == 2  # candidate index 1 failed, 0 and 2 succeeded
    assert [c.candidate_index for c in result.candidates] == [0, 2]


def test_without_a_scene_analysis_the_original_specification_is_used_unchanged(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Phase 10.4's Creative Intelligence integration - a slide with no
    SceneAnalysis (the ordinary case for every test in this file, none
    of which run SceneIntelligenceStage) must compile exactly the
    original, un-enriched Creative Specification - no behavior change
    for slideshows that predate this sub-phase.
    """
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    fake_image_provider = FakeImageGenerationProvider()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=fake_image_provider),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    original_background = creative_specification.structured_json["background_environment"]
    plan = decide_generation_plan("fast")

    run_generation_attempt(db_session, slide, creative_specification, plan)

    assert original_background in fake_image_provider.last_request.creative_intent


def test_with_a_scene_analysis_the_optimized_description_replaces_the_background(
    db_session, slideshow_with_product, monkeypatch
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    original_background = creative_specification.structured_json["background_environment"]

    scene_analysis = SceneAnalysis(
        slide_id=slide.id,
        analysis_run_id="does-not-exist",
        regions_json=[
            {"region_type": "product", "importance_tier": "essential", "notes": "The bottle."},
            {"region_type": "environment", "importance_tier": "context", "notes": "Plain backdrop."},
        ],
    )
    db_session.add(scene_analysis)
    db_session.flush()
    slide.current_scene_analysis_id = scene_analysis.id
    db_session.commit()

    fake_image_provider = FakeImageGenerationProvider()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=fake_image_provider),
    )

    class _FakeTextProvider:
        model = "fake-text-model"
        provider = "openai"

        def generate(self, prompt_spec, response_schema):
            return {
                "optimized_scene_description": "a premium sunlit loft with warm natural light",
                "reasoning": "elevates the brand positioning",
            }

    class _FakeRegistryForText:
        def text_generation(self):
            return _FakeTextProvider()

    monkeypatch.setattr(
        "app.services.creative_intelligence.default_registry", _FakeRegistryForText()
    )

    plan = decide_generation_plan("fast", creativity_level="bold")

    run_generation_attempt(db_session, slide, creative_specification, plan)

    assert "a premium sunlit loft with warm natural light" in fake_image_provider.last_request.creative_intent
    assert original_background not in fake_image_provider.last_request.creative_intent
    # The persisted CreativeSpecification row itself is never mutated.
    db_session.refresh(creative_specification)
    assert creative_specification.structured_json["background_environment"] == original_background


def test_compiled_prompt_includes_the_products_own_branding_text(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): Stage 2 validation's
    branding_text field_check compares against the current Product Lock
    Profile's labels_and_text - previously never surfaced to the model,
    so it failed almost every real attempt. FakeVisionAnalysisProvider's
    default canned profile (see tests/fakes.py) includes
    labels_and_text=[{"text": "Sunrise", ...}], so a full-prerequisites
    run must carry "Sunrise" into the compiled creative_intent.
    """
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    fake_image_provider = FakeImageGenerationProvider()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=fake_image_provider),
    )

    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("fast")

    run_generation_attempt(db_session, slide, creative_specification, plan)

    assert '"Sunrise"' in fake_image_provider.last_request.creative_intent
    assert "reproduce it verbatim" in fake_image_provider.last_request.creative_intent
