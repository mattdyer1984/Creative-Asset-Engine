"""
Unit tests for the Quality Engine (Phase 10.2 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §13).
No real vision call - FakeVisionAnalysisProvider throughout.
"""

from app.models.quality_assessment import QualityAssessment
from app.services.decision_engine import decide_generation_plan
from app.services.generation_engine import run_generation_attempt
from app.services.quality_engine import assess_candidate
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider, FakeVisionAnalysisProvider
from tests.test_generation_engine import _get_creative_specification
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


def test_passing_candidate_is_accepted_with_a_confidence_score_of_one(
    db_session, slideshow_with_product, monkeypatch
):
    candidate = _generate_one_candidate(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(
                results_by_schema_name={
                    "identity_validation": _IDENTITY_PASSES,
                    "image_validation": _CREATIVE_PASSES,
                }
            )
        ),
    )

    assessment = assess_candidate(db_session, candidate)

    assert isinstance(assessment, QualityAssessment)
    assert assessment.accepted is True
    assert assessment.overall_confidence_score == 1.0
    assert assessment.generated_image_id == candidate.id
    assert assessment.creative_fidelity_json is None
    assert assessment.photorealism_json is None
    assert assessment.text_quality_json is None


def test_failing_candidate_is_rejected_with_a_confidence_score_of_zero(
    db_session, slideshow_with_product, monkeypatch
):
    candidate = _generate_one_candidate(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(
                results_by_schema_name={
                    "identity_validation": _IDENTITY_PASSES,
                    "image_validation": _CREATIVE_FAILS,
                }
            )
        ),
    )

    assessment = assess_candidate(db_session, candidate)

    assert assessment.accepted is False
    assert assessment.overall_confidence_score == 0.0


def test_assessment_is_persisted_and_linked_to_the_real_validation_result(
    db_session, slideshow_with_product, monkeypatch
):
    candidate = _generate_one_candidate(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(
                results_by_schema_name={
                    "identity_validation": _IDENTITY_PASSES,
                    "image_validation": _CREATIVE_PASSES,
                }
            )
        ),
    )

    assessment = assess_candidate(db_session, candidate)

    stored = db_session.get(QualityAssessment, assessment.id)
    assert stored is not None
    from app.models.image_validation_result import ImageValidationResult

    validation_result = db_session.get(ImageValidationResult, stored.image_validation_result_id)
    assert validation_result.generated_image_id == candidate.id
    assert validation_result.passed is True
