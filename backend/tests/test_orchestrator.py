"""
Integration tests for AnalysisOrchestrator (plan §13: full pipeline with
a mocked AI provider, including a deliberate mid-pipeline failure).
"""

from app.models.creative_blueprint import STATUS_FAILED, STATUS_READY
from app.models.marketing_analysis import MarketingAnalysis
from app.orchestrator import AnalysisOrchestrator
from app.stages.base import StageResult
from app.stages.ocr_stage import OCRStage
from tests.fakes import FakeAIProviderRegistry, FakeOCRProvider


def test_full_pipeline_succeeds(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = AnalysisOrchestrator(stages=[OCRStage()])
    orchestrator.run_full_pipeline(db_session, creative_with_blueprint)

    db_session.refresh(creative_with_blueprint.blueprint)
    assert creative_with_blueprint.blueprint.status == STATUS_READY
    assert creative_with_blueprint.blueprint.current_ocr_result_id is not None


def test_full_pipeline_marks_failed_on_stage_failure(db_session, creative_with_blueprint, monkeypatch):
    failing_registry = FakeAIProviderRegistry(
        ocr_provider=FakeOCRProvider(raise_error=RuntimeError("boom"))
    )
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", failing_registry)

    orchestrator = AnalysisOrchestrator(stages=[OCRStage()])
    orchestrator.run_full_pipeline(db_session, creative_with_blueprint)

    db_session.refresh(creative_with_blueprint.blueprint)
    assert creative_with_blueprint.blueprint.status == STATUS_FAILED
    assert creative_with_blueprint.blueprint.current_ocr_result_id is None


def test_full_pipeline_return_value_names_the_failed_stage(db_session, creative_with_blueprint, monkeypatch):
    """
    Directly tests run_full_pipeline's return value, added for M7: without
    it, a stage that fails on a prerequisite check before creating any
    AnalysisRun (correct, established behavior for missing prerequisites)
    would leave nothing for the assembled Blueprint view to point to when
    explaining "what failed" - the caller needs this returned directly,
    not reconstructed from AnalysisRun history after the fact.
    """
    monkeypatch.setattr(
        "app.stages.ocr_stage.default_registry",
        FakeAIProviderRegistry(ocr_provider=FakeOCRProvider(raise_error=RuntimeError("boom"))),
    )

    orchestrator = AnalysisOrchestrator(stages=[OCRStage()])
    failed_stage, result = orchestrator.run_full_pipeline(db_session, creative_with_blueprint)

    assert failed_stage == "ocr"
    assert result.succeeded is False
    assert "boom" in result.error


def test_full_pipeline_return_value_is_none_on_success(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = AnalysisOrchestrator(stages=[OCRStage()])
    failed_stage, result = orchestrator.run_full_pipeline(db_session, creative_with_blueprint)

    assert failed_stage is None
    assert result.succeeded is True


class _AlwaysFailsStage:
    name = "always_fails"

    def run(self, db, creative, blueprint):
        return StageResult(succeeded=False, error="deliberate test failure")


def test_failure_isolation_earlier_stage_output_untouched(db_session, creative_with_blueprint, monkeypatch):
    """
    A stub second stage that always fails, following a real OCR stage that
    succeeds - proves a downstream failure doesn't corrupt or roll back an
    earlier stage's already-committed output (plan §6.3).
    """
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = AnalysisOrchestrator(stages=[OCRStage(), _AlwaysFailsStage()])
    orchestrator.run_full_pipeline(db_session, creative_with_blueprint)

    db_session.refresh(creative_with_blueprint.blueprint)
    assert creative_with_blueprint.blueprint.status == STATUS_FAILED
    # OCR's output survives even though the pipeline as a whole failed.
    assert creative_with_blueprint.blueprint.current_ocr_result_id is not None


def test_run_single_stage_reruns_in_isolation(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    orchestrator = AnalysisOrchestrator(stages=[OCRStage()])
    orchestrator.run_full_pipeline(db_session, creative_with_blueprint)
    db_session.refresh(creative_with_blueprint.blueprint)
    first_id = creative_with_blueprint.blueprint.current_ocr_result_id

    result = orchestrator.run_single_stage(db_session, creative_with_blueprint, "ocr")

    db_session.refresh(creative_with_blueprint.blueprint)
    assert result.succeeded is True
    assert creative_with_blueprint.blueprint.status == STATUS_READY
    # A new version was created, not the same row reused.
    assert creative_with_blueprint.blueprint.current_ocr_result_id != first_id


def test_rerunning_upstream_stage_alone_does_not_touch_downstream_artifacts(
    db_session, creative_with_blueprint, monkeypatch
):
    """
    Directly answers a review question: rerunning just Creative Fingerprint
    (in isolation, via run_single_stage - not a full pipeline re-run) must
    leave the existing Marketing Analysis - built from the OLD fingerprint
    - completely untouched, both its own is_current flag and the
    Blueprint's current_marketing_analysis_id pointer. No automatic
    invalidation of downstream artifacts is the explicitly desired
    behavior; this proves it holds, rather than just citing that
    CreativeFingerprintStage never references MarketingAnalysis in its
    source.
    """
    from app.stages.creative_fingerprint_stage import CreativeFingerprintStage
    from app.stages.marketing_analysis_stage import MarketingAnalysisStage
    from tests.fakes import FakeVisionAnalysisProvider
    from tests.test_creative_fingerprint_stage import FINGERPRINT_RESULT

    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )

    orchestrator = AnalysisOrchestrator(
        stages=[CreativeFingerprintStage(), MarketingAnalysisStage()]
    )
    orchestrator.run_full_pipeline(db_session, creative_with_blueprint)

    db_session.refresh(creative_with_blueprint.blueprint)
    original_fingerprint_id = creative_with_blueprint.blueprint.current_creative_fingerprint_id
    original_marketing_analysis_id = creative_with_blueprint.blueprint.current_marketing_analysis_id
    assert original_fingerprint_id is not None
    assert original_marketing_analysis_id is not None

    # Rerun ONLY Creative Fingerprint, in isolation - not the whole pipeline.
    orchestrator.run_single_stage(db_session, creative_with_blueprint, "creative_fingerprint")

    db_session.refresh(creative_with_blueprint.blueprint)
    new_fingerprint_id = creative_with_blueprint.blueprint.current_creative_fingerprint_id
    assert new_fingerprint_id != original_fingerprint_id  # Fingerprint DID get a new version

    # Marketing Analysis must be completely untouched.
    assert creative_with_blueprint.blueprint.current_marketing_analysis_id == original_marketing_analysis_id
    untouched_marketing_analysis = db_session.get(MarketingAnalysis, original_marketing_analysis_id)
    assert untouched_marketing_analysis.is_current is True


def test_default_pipeline_runs_all_six_stages(db_session, creative_with_product, monkeypatch):
    """
    Integration test against the REAL default STAGE_PIPELINE (not an
    explicit stages=[...] override), using creative_with_product so
    Product Isolation and Product Lock Profile's prerequisite
    (product_id) is met - proves the plan's 'add a stage, no other
    changes' extension story actually holds for the pipeline as shipped,
    not just for hand-picked stage lists in other tests.
    """
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    orchestrator = AnalysisOrchestrator()  # uses the real STAGE_PIPELINE
    orchestrator.run_full_pipeline(db_session, creative_with_product)

    db_session.refresh(creative_with_product.blueprint)
    blueprint = creative_with_product.blueprint
    assert blueprint.status == STATUS_READY
    assert blueprint.current_ocr_result_id is not None
    assert blueprint.current_product_lock_profile_id is not None
    assert blueprint.current_creative_fingerprint_id is not None
    assert blueprint.current_marketing_analysis_id is not None
    assert blueprint.current_recreation_prompt_id is not None
