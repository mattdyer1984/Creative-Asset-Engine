"""
Integration tests for SlideshowOrchestrator (new pipeline, Phase 2.4e) -
mirrors tests/test_orchestrator.py's coverage of AnalysisOrchestrator.
"""

from sqlalchemy import select

from app.models.marketing_analysis import MarketingAnalysis
from app.models.product_lock_profile import ProductLockProfile
from app.models.slideshow import STATUS_FAILED, STATUS_READY
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.ocr_stage import SlideOCRStage
from app.slideshow_stages.orchestrator import SlideshowOrchestrator
from tests.fakes import (
    FakeAIProviderRegistry,
    FakeOCRProvider,
    FakeTextGenerationProvider,
    FakeVisionAnalysisProvider,
)


def test_full_pipeline_succeeds(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = SlideshowOrchestrator(stages=[SlideOCRStage()])
    orchestrator.run_full_pipeline(db_session, slideshow_with_slide)

    db_session.refresh(slideshow_with_slide)
    assert slideshow_with_slide.status == STATUS_READY
    assert slideshow_with_slide.primary_slide.current_ocr_result_id is not None


def test_full_pipeline_marks_failed_on_stage_failure(db_session, slideshow_with_slide, monkeypatch):
    failing_registry = FakeAIProviderRegistry(
        ocr_provider=FakeOCRProvider(raise_error=RuntimeError("boom"))
    )
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", failing_registry)

    orchestrator = SlideshowOrchestrator(stages=[SlideOCRStage()])
    orchestrator.run_full_pipeline(db_session, slideshow_with_slide)

    db_session.refresh(slideshow_with_slide)
    assert slideshow_with_slide.status == STATUS_FAILED
    assert slideshow_with_slide.primary_slide.current_ocr_result_id is None


def test_full_pipeline_return_value_names_the_failed_stage(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.ocr_stage.default_registry",
        FakeAIProviderRegistry(ocr_provider=FakeOCRProvider(raise_error=RuntimeError("boom"))),
    )

    orchestrator = SlideshowOrchestrator(stages=[SlideOCRStage()])
    failed_stage, result = orchestrator.run_full_pipeline(db_session, slideshow_with_slide)

    assert failed_stage == "ocr"
    assert result.succeeded is False
    assert "boom" in result.error


def test_full_pipeline_return_value_is_none_on_success(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = SlideshowOrchestrator(stages=[SlideOCRStage()])
    failed_stage, result = orchestrator.run_full_pipeline(db_session, slideshow_with_slide)

    assert failed_stage is None
    assert result.succeeded is True


class _AlwaysFailsStage:
    name = "always_fails"

    def run(self, db, slideshow):
        return StageResult(succeeded=False, error="deliberate test failure")


def test_failure_isolation_earlier_stage_output_untouched(db_session, slideshow_with_slide, monkeypatch):
    """A stub second stage that always fails, following a real OCR stage that succeeds."""
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = SlideshowOrchestrator(stages=[SlideOCRStage(), _AlwaysFailsStage()])
    orchestrator.run_full_pipeline(db_session, slideshow_with_slide)

    db_session.refresh(slideshow_with_slide)
    assert slideshow_with_slide.status == STATUS_FAILED
    assert slideshow_with_slide.primary_slide.current_ocr_result_id is not None


def test_run_single_stage_reruns_in_isolation(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = SlideshowOrchestrator(stages=[SlideOCRStage()])
    orchestrator.run_full_pipeline(db_session, slideshow_with_slide)
    db_session.refresh(slideshow_with_slide)
    first_id = slideshow_with_slide.primary_slide.current_ocr_result_id

    result = orchestrator.run_single_stage(db_session, slideshow_with_slide, "ocr")

    db_session.refresh(slideshow_with_slide)
    assert result.succeeded is True
    assert slideshow_with_slide.status == STATUS_READY
    assert slideshow_with_slide.primary_slide.current_ocr_result_id != first_id


def test_rerunning_upstream_stage_alone_does_not_touch_downstream_artifacts(
    db_session, slideshow_with_slide, monkeypatch
):
    """
    Rerunning just Creative Fingerprint (in isolation via
    run_single_stage) must leave the existing Marketing Analysis - built
    from the OLD fingerprint - completely untouched.
    """
    from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
    from app.slideshow_stages.marketing_analysis_stage import SlideshowMarketingAnalysisStage
    from tests.fakes import FakeVisionAnalysisProvider
    from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT

    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )

    orchestrator = SlideshowOrchestrator(
        stages=[SlideCreativeFingerprintStage(), SlideshowMarketingAnalysisStage()]
    )
    orchestrator.run_full_pipeline(db_session, slideshow_with_slide)

    db_session.refresh(slideshow_with_slide)
    original_fingerprint_id = slideshow_with_slide.primary_slide.current_creative_fingerprint_id
    original_marketing_analysis_id = slideshow_with_slide.current_marketing_analysis_id
    assert original_fingerprint_id is not None
    assert original_marketing_analysis_id is not None

    orchestrator.run_single_stage(db_session, slideshow_with_slide, "creative_fingerprint")

    db_session.refresh(slideshow_with_slide)
    new_fingerprint_id = slideshow_with_slide.primary_slide.current_creative_fingerprint_id
    assert new_fingerprint_id != original_fingerprint_id

    assert slideshow_with_slide.current_marketing_analysis_id == original_marketing_analysis_id
    untouched_marketing_analysis = db_session.get(MarketingAnalysis, original_marketing_analysis_id)
    assert untouched_marketing_analysis.is_current is True


def test_default_pipeline_runs_all_seven_stages(db_session, slideshow_with_product, monkeypatch):
    """
    Integration test against the REAL default SLIDESHOW_STAGE_PIPELINE
    (not an explicit stages=[...] override), using slideshow_with_product
    so Product Isolation and Product Lock Profile's prerequisite (a
    current ProductAppearance) is met. Seven stages as of Phase 7.2
    (Narrative Structure, see MIGRATION_PLAN.md) - was six.

    Unlike the old test's blueprint.current_product_lock_profile_id
    assertion, this checks for a current ProductLockProfile row directly -
    there is deliberately no such pointer on Slide/Slideshow (see Phase
    2.4b's docstring on why).
    """
    for module in (
        "app.slideshow_stages.ocr_stage",
        "app.slideshow_stages.product_isolation_stage",
        "app.slideshow_stages.product_lock_profile_stage",
        "app.slideshow_stages.creative_fingerprint_stage",
        "app.slideshow_stages.marketing_analysis_stage",
        "app.slideshow_stages.creative_specification_stage",
    ):
        monkeypatch.setattr(f"{module}.default_registry", FakeAIProviderRegistry())
    # Phase 10.4 (Scene Intelligence, see MIGRATION_PLAN.md) added a real
    # vision call between Creative Fingerprint and Marketing Analysis in
    # SLIDESHOW_STAGE_PIPELINE - a real, pre-existing gap found while
    # building Phase 12: this test never patched it, so it was silently
    # making a real, paid vision call. Needs its own fake registry (not
    # the shared-shape one above) since its schema requires a "regions"
    # key the generic FakeVisionAnalysisProvider default doesn't return.
    monkeypatch.setattr(
        "app.slideshow_stages.scene_intelligence_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result={"regions": []})),
    )
    # Narrative Structure (Phase 7.2) shares TextGenerationProvider with
    # Marketing Analysis but expects a different response shape - its own
    # fake registry, not the shared-shape one above.
    monkeypatch.setattr(
        "app.slideshow_stages.narrative_structure_stage.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(
                result={"slides": [{"slide_index": 0, "beat": "hook"}], "arc_summary": "A short arc."}
            )
        ),
    )

    orchestrator = SlideshowOrchestrator()  # uses the real SLIDESHOW_STAGE_PIPELINE
    orchestrator.run_full_pipeline(db_session, slideshow_with_product)

    db_session.refresh(slideshow_with_product)
    slide = slideshow_with_product.primary_slide
    assert slideshow_with_product.status == STATUS_READY
    assert slide.current_ocr_result_id is not None
    assert slide.current_creative_fingerprint_id is not None
    assert slideshow_with_product.current_marketing_analysis_id is not None
    assert slideshow_with_product.current_narrative_structure_id is not None
    assert slideshow_with_product.current_creative_specification_id is not None

    product_id = slide.product_appearances[0].product_id
    current_lock_profile = db_session.scalars(
        select(ProductLockProfile).where(
            ProductLockProfile.product_id == product_id,
            ProductLockProfile.is_current.is_(True),
        )
    ).first()
    assert current_lock_profile is not None
