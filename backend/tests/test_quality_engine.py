"""
Unit tests for the Quality Engine (Phase 10.2 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §13;
Photorealism dimension added Phase 10.3). No real vision call -
FakeVisionAnalysisProvider throughout.
"""

from app.models.creative_specification import CreativeSpecification
from app.models.quality_assessment import QualityAssessment
from app.services.decision_engine import decide_generation_plan
from app.services.generation_engine import run_generation_attempt, run_story_generation_attempt
from app.services.quality_engine import (
    PHOTOREALISM_FLOOR,
    _score_photorealism,
    assess_candidate,
    assess_story_candidate,
)
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider, FakeVisionAnalysisProvider
from tests.test_generation_engine import _build_story_slide_prerequisites, _get_creative_specification
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
_PHOTOREALISM_FAILS = {
    "realistic_lighting": False,
    "believable_shadows": False,
    "material_accuracy": False,
    "reflections_correct": False,
    "texture_quality": "poor",
    "perspective_correct": False,
    "object_integrity": False,
    "human_anatomy": "incorrect",
    "ai_artefacts_detected": True,
    "image_sharpness": "poor",
    "reasons": ["obviously synthetic, warped geometry"],
}


def _generate_one_candidate(db_session, slideshow_with_product, monkeypatch):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )
    slide = slideshow_with_product.primary_slide
    creative_specification = _get_creative_specification(db_session, slideshow_with_product)
    plan = decide_generation_plan("fast")
    result = run_generation_attempt(db_session, slide, creative_specification, plan)
    return result.candidates[0]


def _generate_one_story_candidate(db_session, slideshow_with_slide, monkeypatch):
    _build_story_slide_prerequisites(db_session, slideshow_with_slide, monkeypatch)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )
    slide = slideshow_with_slide.primary_slide
    creative_specification = db_session.get(CreativeSpecification, slide.current_creative_specification_id)
    plan = decide_generation_plan("fast")
    result = run_story_generation_attempt(db_session, slide, creative_specification, plan)
    return result.candidates[0]


def test_passing_fidelity_and_photorealism_is_accepted_with_a_confidence_score_of_one(
    db_session, slideshow_with_product, monkeypatch
):
    candidate = _generate_one_candidate(db_session, slideshow_with_product, monkeypatch)
    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": _CREATIVE_PASSES,
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

    assessment = assess_candidate(db_session, candidate)

    assert isinstance(assessment, QualityAssessment)
    assert assessment.accepted is True
    assert assessment.overall_confidence_score == 1.0
    assert assessment.generated_image_id == candidate.id
    assert assessment.creative_fidelity_json is None
    assert assessment.photorealism_json == _PHOTOREALISM_PASSES
    assert assessment.text_quality_json is None


def test_failing_fidelity_is_rejected_without_spending_a_photorealism_call(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Product Fidelity is a hard floor - a failure here must short-circuit
    before Photorealism ever runs, saving a real vision call on a
    candidate already disqualified for a different reason.
    """
    candidate = _generate_one_candidate(db_session, slideshow_with_product, monkeypatch)
    photorealism_calls = {"n": 0}

    class _CountingVisionProvider:
        model = "fake-vision-model"
        provider = "openai"

        def analyze_creative(self, image_bytes, prompt_spec, response_schema, *, usage_sink=None):
            schema_name = prompt_spec.get("schema_name")
            if schema_name == "identity_validation":
                return _IDENTITY_PASSES
            if schema_name == "image_validation":
                return _CREATIVE_FAILS
            photorealism_calls["n"] += 1
            return _PHOTOREALISM_PASSES

    counting_provider = _CountingVisionProvider()
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=counting_provider),
    )
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=counting_provider),
    )

    assessment = assess_candidate(db_session, candidate)

    assert assessment.accepted is False
    assert assessment.overall_confidence_score == 0.0
    assert assessment.photorealism_json is None
    assert photorealism_calls["n"] == 0


def test_passing_fidelity_but_poor_photorealism_is_rejected(
    db_session, slideshow_with_product, monkeypatch
):
    candidate = _generate_one_candidate(db_session, slideshow_with_product, monkeypatch)
    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": _CREATIVE_PASSES,
            "photorealism": _PHOTOREALISM_FAILS,
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

    assessment = assess_candidate(db_session, candidate)

    assert assessment.accepted is False
    assert assessment.overall_confidence_score == 0.0
    assert assessment.photorealism_json == _PHOTOREALISM_FAILS


def test_assessment_is_persisted_and_linked_to_the_real_validation_result(
    db_session, slideshow_with_product, monkeypatch
):
    candidate = _generate_one_candidate(db_session, slideshow_with_product, monkeypatch)
    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": _CREATIVE_PASSES,
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

    assessment = assess_candidate(db_session, candidate)

    stored = db_session.get(QualityAssessment, assessment.id)
    assert stored is not None
    from app.models.image_validation_result import ImageValidationResult

    validation_result = db_session.get(ImageValidationResult, stored.image_validation_result_id)
    assert validation_result.generated_image_id == candidate.id
    assert validation_result.passed is True


def test_score_photorealism_perfect_result_scores_one():
    assert _score_photorealism(_PHOTOREALISM_PASSES) == 1.0


def test_score_photorealism_worst_result_scores_zero():
    assert _score_photorealism(_PHOTOREALISM_FAILS) == 0.0


def test_score_photorealism_human_anatomy_not_applicable_does_not_penalize():
    """Most product-ad images have no humans at all - "not_applicable" must score like "correct", never like "incorrect"."""
    not_applicable_result = {**_PHOTOREALISM_PASSES, "human_anatomy": "not_applicable"}
    correct_result = {**_PHOTOREALISM_PASSES, "human_anatomy": "correct"}
    assert _score_photorealism(not_applicable_result) == _score_photorealism(correct_result)


def test_score_photorealism_floor_is_a_real_threshold_not_a_token_gate():
    # A candidate that's mediocre-but-not-terrible across every axis
    # should land below the floor, not scrape a pass.
    mediocre_result = {
        "realistic_lighting": True,
        "believable_shadows": False,
        "material_accuracy": True,
        "reflections_correct": False,
        "texture_quality": "fair",
        "perspective_correct": True,
        "object_integrity": False,
        "human_anatomy": "not_applicable",
        "ai_artefacts_detected": True,
        "image_sharpness": "fair",
        "reasons": ["mixed quality"],
    }
    score = _score_photorealism(mediocre_result)
    assert score < PHOTOREALISM_FLOOR


def test_assess_story_candidate_accepts_on_good_photorealism_alone(db_session, slideshow_with_slide, monkeypatch):
    """
    Story Slide feature (see MIGRATION_PLAN.md): no product, no Product
    Profile, no reference set - acceptance is Photorealism alone, with
    no Stage 1/Stage 2 floor to clear first.
    """
    candidate = _generate_one_story_candidate(db_session, slideshow_with_slide, monkeypatch)
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=_PHOTOREALISM_PASSES)),
    )

    assessment = assess_story_candidate(db_session, candidate)

    assert isinstance(assessment, QualityAssessment)
    assert assessment.accepted is True
    assert assessment.image_validation_result_id is None
    assert assessment.overall_confidence_score == _score_photorealism(_PHOTOREALISM_PASSES)


def test_assess_story_candidate_rejects_on_poor_photorealism(db_session, slideshow_with_slide, monkeypatch):
    candidate = _generate_one_story_candidate(db_session, slideshow_with_slide, monkeypatch)
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=_PHOTOREALISM_FAILS)),
    )

    assessment = assess_story_candidate(db_session, candidate)

    assert assessment.accepted is False


def test_assess_story_candidate_is_persisted(db_session, slideshow_with_slide, monkeypatch):
    candidate = _generate_one_story_candidate(db_session, slideshow_with_slide, monkeypatch)
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=_PHOTOREALISM_PASSES)),
    )

    assessment = assess_story_candidate(db_session, candidate)

    stored = db_session.get(QualityAssessment, assessment.id)
    assert stored is not None
    assert stored.generated_image_id == candidate.id
