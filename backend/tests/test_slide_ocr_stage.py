"""
Unit tests for SlideOCRStage (new pipeline, Phase 2.4a) - mirrors
tests/test_ocr_stage.py's coverage of the old OCRStage.
"""

from sqlalchemy import select

from app.ai_providers.base import OCRExtraction
from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.models.ocr_result import OCRResult
from app.slideshow_stages.ocr_stage import SlideOCRStage
from tests.fakes import FakeAIProviderRegistry, FakeOCRProvider


def test_slide_ocr_stage_succeeds_and_updates_slide(db_session, slideshow_with_slide, monkeypatch):
    fake_registry = FakeAIProviderRegistry()
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", fake_registry)

    stage = SlideOCRStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is True
    assert result.error is None

    db_session.refresh(slideshow_with_slide.slide)
    ocr_result_id = slideshow_with_slide.slide.current_ocr_result_id
    assert ocr_result_id is not None

    ocr_result = db_session.get(OCRResult, ocr_result_id)
    assert ocr_result.raw_text == "Fresh Squeezed. Zero Sugar Added."
    assert ocr_result.is_current is True
    assert ocr_result.slide_id == slideshow_with_slide.slide.id
    assert ocr_result.creative_id is None  # new pipeline never writes the legacy FK
    assert ocr_result.structured_blocks_json[0]["role"] == "headline"

    analysis_run = db_session.get(AnalysisRun, ocr_result.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "ocr"
    assert analysis_run.model_name == "fake-ocr-model"
    assert analysis_run.slide_id == slideshow_with_slide.slide.id
    assert analysis_run.creative_id is None


def test_slide_ocr_stage_fails_gracefully_on_provider_error(db_session, slideshow_with_slide, monkeypatch):
    fake_registry = FakeAIProviderRegistry(
        ocr_provider=FakeOCRProvider(raise_error=RuntimeError("provider timed out"))
    )
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", fake_registry)

    stage = SlideOCRStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "provider timed out" in result.error

    db_session.refresh(slideshow_with_slide.slide)
    assert slideshow_with_slide.slide.current_ocr_result_id is None

    runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(runs) == 1
    assert runs[0].status == STATUS_FAILED
    assert "provider timed out" in runs[0].error


def test_slide_ocr_stage_is_independently_rerunnable(db_session, slideshow_with_slide, monkeypatch):
    """Rerunning creates a new version and flips is_current, never mutating the old row."""
    fake_registry = FakeAIProviderRegistry()
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", fake_registry)

    stage = SlideOCRStage()
    stage.run(db_session, slideshow_with_slide)
    first_ocr_result_id = slideshow_with_slide.slide.current_ocr_result_id

    fake_registry._ocr_provider = FakeOCRProvider(
        extraction=OCRExtraction(raw_text="Updated text", structured_blocks=[])
    )
    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slideshow_with_slide.slide)
    second_ocr_result_id = slideshow_with_slide.slide.current_ocr_result_id

    assert second_ocr_result_id != first_ocr_result_id

    first_result = db_session.get(OCRResult, first_ocr_result_id)
    second_result = db_session.get(OCRResult, second_ocr_result_id)
    assert first_result.is_current is False
    assert first_result.raw_text == "Fresh Squeezed. Zero Sugar Added."  # untouched
    assert second_result.is_current is True
    assert second_result.raw_text == "Updated text"

    all_runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(all_runs) == 2
