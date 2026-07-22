"""
Unit tests for SlideOCRStage (new pipeline, Phase 2.4a) - mirrors
tests/test_ocr_stage.py's coverage of the old OCRStage. Phase 7.1
(Narrative pass, see MIGRATION_PLAN.md) widened this stage to run across
every slide, not just primary_slide - the multi-slide tests below are
that sub-phase's own coverage.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.ai_providers.base import OCRExtraction
from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.models.ocr_result import OCRResult
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.slideshow_stages.ocr_stage import SlideOCRStage
from tests.fakes import FakeAIProviderRegistry, FakeOCRProvider


def test_slide_ocr_stage_succeeds_and_updates_slide(db_session, slideshow_with_slide, monkeypatch):
    fake_registry = FakeAIProviderRegistry()
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", fake_registry)

    stage = SlideOCRStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is True
    assert result.error is None

    db_session.refresh(slideshow_with_slide.primary_slide)
    ocr_result_id = slideshow_with_slide.primary_slide.current_ocr_result_id
    assert ocr_result_id is not None

    ocr_result = db_session.get(OCRResult, ocr_result_id)
    assert ocr_result.raw_text == "Fresh Squeezed. Zero Sugar Added."
    assert ocr_result.is_current is True
    assert ocr_result.slide_id == slideshow_with_slide.primary_slide.id
    assert ocr_result.creative_id is None  # new pipeline never writes the legacy FK
    assert ocr_result.structured_blocks_json[0]["role"] == "headline"

    analysis_run = db_session.get(AnalysisRun, ocr_result.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "ocr"
    assert analysis_run.model_name == "fake-ocr-model"
    assert analysis_run.slide_id == slideshow_with_slide.primary_slide.id
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

    db_session.refresh(slideshow_with_slide.primary_slide)
    assert slideshow_with_slide.primary_slide.current_ocr_result_id is None

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
    first_ocr_result_id = slideshow_with_slide.primary_slide.current_ocr_result_id

    fake_registry._ocr_provider = FakeOCRProvider(
        extraction=OCRExtraction(raw_text="Updated text", structured_blocks=[])
    )
    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slideshow_with_slide.primary_slide)
    second_ocr_result_id = slideshow_with_slide.primary_slide.current_ocr_result_id

    assert second_ocr_result_id != first_ocr_result_id

    first_result = db_session.get(OCRResult, first_ocr_result_id)
    second_result = db_session.get(OCRResult, second_ocr_result_id)
    assert first_result.is_current is False
    assert first_result.raw_text == "Fresh Squeezed. Zero Sugar Added."  # untouched
    assert second_result.is_current is True
    assert second_result.raw_text == "Updated text"

    all_runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(all_runs) == 2


def _make_multi_slide_slideshow(db_session, tmp_path, slide_count: int) -> Slideshow:
    slideshow = Slideshow(imported_at=datetime.now(timezone.utc))
    db_session.add(slideshow)
    db_session.flush()

    for i in range(slide_count):
        image_path = tmp_path / f"slide-{i}.jpg"
        image_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
        db_session.add(
            Slide(
                slideshow_id=slideshow.id,
                slide_index=i,
                stored_file_path=str(image_path),
                original_filename=f"slide-{i}.jpg",
                source_type="local_file",
                source_locator=f"slide-{i}.jpg",
            )
        )
    db_session.commit()
    db_session.refresh(slideshow)
    return slideshow


class _SequentialFakeOCRProvider:
    """Returns a distinct extraction per call, in order - proves each slide gets its own OCR, not one repeated."""

    model = "fake-ocr-model"
    provider = "openai"

    def __init__(self, extractions: list[OCRExtraction]):
        self._extractions = extractions
        self._call_count = 0

    def extract_text(self, image_bytes: bytes) -> OCRExtraction:
        extraction = self._extractions[self._call_count]
        self._call_count += 1
        return extraction


def test_ocr_stage_runs_on_every_slide_in_a_multi_slide_slideshow(db_session, tmp_path, monkeypatch):
    slideshow = _make_multi_slide_slideshow(db_session, tmp_path, slide_count=3)
    extractions = [
        OCRExtraction(raw_text=f"Slide {i} text", structured_blocks=[{"text": f"Slide {i}", "role": "headline"}])
        for i in range(3)
    ]
    fake_registry = FakeAIProviderRegistry(ocr_provider=_SequentialFakeOCRProvider(extractions))
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", fake_registry)

    stage = SlideOCRStage()
    result = stage.run(db_session, slideshow)

    assert result.succeeded is True
    for i, slide in enumerate(sorted(slideshow.slides, key=lambda s: s.slide_index)):
        db_session.refresh(slide)
        assert slide.current_ocr_result_id is not None
        ocr_result = db_session.get(OCRResult, slide.current_ocr_result_id)
        assert ocr_result.raw_text == f"Slide {i} text"
        assert ocr_result.slide_id == slide.id


def test_ocr_stage_fails_the_whole_stage_if_any_slide_fails(db_session, tmp_path, monkeypatch):
    """
    One slide's OCR failure fails the stage - slides processed before the
    failing one keep their already-committed results, per the stage's own
    documented "honest failure" behavior (see MIGRATION_PLAN.md's Phase
    7.1 report).
    """
    slideshow = _make_multi_slide_slideshow(db_session, tmp_path, slide_count=3)

    class _FailOnSecondCallOCRProvider:
        model = "fake-ocr-model"
        provider = "openai"

        def __init__(self):
            self._call_count = 0

        def extract_text(self, image_bytes: bytes) -> OCRExtraction:
            self._call_count += 1
            if self._call_count == 2:
                raise RuntimeError("provider timed out on slide 2")
            return OCRExtraction(raw_text="ok", structured_blocks=[])

    fake_registry = FakeAIProviderRegistry(ocr_provider=_FailOnSecondCallOCRProvider())
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", fake_registry)

    stage = SlideOCRStage()
    result = stage.run(db_session, slideshow)

    assert result.succeeded is False
    assert "provider timed out on slide 2" in result.error

    slides = sorted(slideshow.slides, key=lambda s: s.slide_index)
    db_session.refresh(slides[0])
    db_session.refresh(slides[1])
    db_session.refresh(slides[2])
    assert slides[0].current_ocr_result_id is not None  # succeeded before the failure
    assert slides[1].current_ocr_result_id is None  # the failing slide
    assert slides[2].current_ocr_result_id is None  # never attempted
