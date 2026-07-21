"""
Unit tests for OCRStage (plan §13's Stage contract tests: succeeds given
valid input, fails gracefully given a provider error, is independently
rerunnable).
"""

from sqlalchemy import select

from app.ai_providers.base import OCRExtraction
from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.models.ocr_result import OCRResult
from app.stages.ocr_stage import OCRStage
from tests.fakes import FakeAIProviderRegistry, FakeOCRProvider


def test_ocr_stage_succeeds_and_updates_blueprint(db_session, creative_with_blueprint, monkeypatch):
    fake_registry = FakeAIProviderRegistry()
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", fake_registry)

    stage = OCRStage()
    result = stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    assert result.succeeded is True
    assert result.error is None

    db_session.refresh(creative_with_blueprint.blueprint)
    ocr_result_id = creative_with_blueprint.blueprint.current_ocr_result_id
    assert ocr_result_id is not None

    ocr_result = db_session.get(OCRResult, ocr_result_id)
    assert ocr_result.raw_text == "Fresh Squeezed. Zero Sugar Added."
    assert ocr_result.is_current is True
    assert ocr_result.structured_blocks_json[0]["role"] == "headline"

    analysis_run = db_session.get(AnalysisRun, ocr_result.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "ocr"
    assert analysis_run.model_name == "fake-ocr-model"


def test_ocr_stage_fails_gracefully_on_provider_error(db_session, creative_with_blueprint, monkeypatch):
    fake_registry = FakeAIProviderRegistry(
        ocr_provider=FakeOCRProvider(raise_error=RuntimeError("provider timed out"))
    )
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", fake_registry)

    stage = OCRStage()
    result = stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    # Never raises - reports failure as data (plan §6.1).
    assert result.succeeded is False
    assert "provider timed out" in result.error

    db_session.refresh(creative_with_blueprint.blueprint)
    assert creative_with_blueprint.blueprint.current_ocr_result_id is None

    runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(runs) == 1
    assert runs[0].status == STATUS_FAILED
    assert "provider timed out" in runs[0].error


def test_ocr_stage_is_independently_rerunnable(db_session, creative_with_blueprint, monkeypatch):
    """Rerunning creates a new version and flips is_current, never mutating the old row."""
    fake_registry = FakeAIProviderRegistry()
    monkeypatch.setattr("app.stages.ocr_stage.default_registry", fake_registry)

    stage = OCRStage()
    stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)
    first_ocr_result_id = creative_with_blueprint.blueprint.current_ocr_result_id

    # Rerun with different fake content.
    fake_registry._ocr_provider = FakeOCRProvider(
        extraction=OCRExtraction(raw_text="Updated text", structured_blocks=[])
    )
    stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)
    db_session.refresh(creative_with_blueprint.blueprint)
    second_ocr_result_id = creative_with_blueprint.blueprint.current_ocr_result_id

    assert second_ocr_result_id != first_ocr_result_id

    first_result = db_session.get(OCRResult, first_ocr_result_id)
    second_result = db_session.get(OCRResult, second_ocr_result_id)
    assert first_result.is_current is False
    assert first_result.raw_text == "Fresh Squeezed. Zero Sugar Added."  # untouched
    assert second_result.is_current is True
    assert second_result.raw_text == "Updated text"

    all_runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(all_runs) == 2
