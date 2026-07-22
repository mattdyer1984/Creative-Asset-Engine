"""
Unit tests for SlideshowNarrativeStructureStage - Phase 7.2 of the
Narrative pass (see MIGRATION_PLAN.md's architecture direction for this
phase). Genuinely new stage, no old-pipeline equivalent to mirror.
"""

from sqlalchemy import select

from app.models.analysis_run import ANALYSIS_TYPE_OCR, STATUS_SUCCEEDED, AnalysisRun
from app.models.narrative_structure import NarrativeStructure
from app.models.ocr_result import OCRResult
from app.models.slide import Slide
from app.slideshow_stages.narrative_structure_stage import (
    BEAT_UNCLASSIFIABLE,
    SlideshowNarrativeStructureStage,
)
from tests.fakes import FakeAIProviderRegistry, FakeTextGenerationProvider


def _set_ocr(db_session, slide: Slide, raw_text: str) -> OCRResult:
    analysis_run = AnalysisRun(
        slide_id=slide.id,
        analysis_type=ANALYSIS_TYPE_OCR,
        provider="fake",
        model_name="fake",
        status=STATUS_SUCCEEDED,
    )
    db_session.add(analysis_run)
    db_session.flush()

    ocr_result = OCRResult(
        analysis_run_id=analysis_run.id, slide_id=slide.id, raw_text=raw_text, structured_blocks_json=[]
    )
    db_session.add(ocr_result)
    db_session.flush()
    slide.current_ocr_result_id = ocr_result.id
    db_session.commit()
    return ocr_result


def test_fails_gracefully_without_any_ocr_text(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.narrative_structure_stage.default_registry", FakeAIProviderRegistry()
    )

    result = SlideshowNarrativeStructureStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "No OCR text" in result.error
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_single_slide_gets_one_beat(db_session, slideshow_with_slide, monkeypatch):
    slide = slideshow_with_slide.primary_slide
    ocr_result = _set_ocr(db_session, slide, "Fresh Squeezed. Zero Sugar Added.")

    fake_registry = FakeAIProviderRegistry(
        text_generation_provider=FakeTextGenerationProvider(
            result={"slides": [{"slide_index": 0, "beat": "hook"}], "arc_summary": "Opens strong on freshness."}
        )
    )
    monkeypatch.setattr("app.slideshow_stages.narrative_structure_stage.default_registry", fake_registry)

    result = SlideshowNarrativeStructureStage().run(db_session, slideshow_with_slide)

    assert result.succeeded is True
    db_session.refresh(slideshow_with_slide)
    narrative = db_session.get(NarrativeStructure, slideshow_with_slide.current_narrative_structure_id)
    assert narrative.is_current is True
    assert narrative.structured_json["slides"] == [{"slide_id": slide.id, "slide_index": 0, "beat": "hook"}]
    assert narrative.structured_json["arc_summary"] == "Opens strong on freshness."
    assert narrative.ocr_result_ids_json == [ocr_result.id]

    analysis_run = db_session.get(AnalysisRun, narrative.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "narrative_structure"
    assert analysis_run.slideshow_id == slideshow_with_slide.id


def _make_multi_slide_slideshow(db_session, tmp_path, texts: list[str]):
    from datetime import datetime, timezone

    from app.models.slideshow import Slideshow

    slideshow = Slideshow(imported_at=datetime.now(timezone.utc))
    db_session.add(slideshow)
    db_session.flush()

    slides = []
    for i, text in enumerate(texts):
        image_path = tmp_path / f"slide-{i}.jpg"
        image_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
        slide = Slide(
            slideshow_id=slideshow.id,
            slide_index=i,
            stored_file_path=str(image_path),
            original_filename=f"slide-{i}.jpg",
            source_type="local_file",
            source_locator=f"slide-{i}.jpg",
        )
        db_session.add(slide)
        db_session.flush()
        if text:
            _set_ocr(db_session, slide, text)
        slides.append(slide)

    db_session.commit()
    db_session.refresh(slideshow)
    return slideshow, slides


def test_multi_slide_gets_distinct_per_slide_beats(db_session, tmp_path, monkeypatch):
    slideshow, slides = _make_multi_slide_slideshow(
        db_session, tmp_path, ["You smell incredible", "Meet the new scent", "Shop now"]
    )

    fake_registry = FakeAIProviderRegistry(
        text_generation_provider=FakeTextGenerationProvider(
            result={
                "slides": [
                    {"slide_index": 0, "beat": "hook"},
                    {"slide_index": 1, "beat": "reveal"},
                    {"slide_index": 2, "beat": "cta"},
                ],
                "arc_summary": "Hook, reveal, then a direct call to action.",
            }
        )
    )
    monkeypatch.setattr("app.slideshow_stages.narrative_structure_stage.default_registry", fake_registry)

    result = SlideshowNarrativeStructureStage().run(db_session, slideshow)

    assert result.succeeded is True
    db_session.refresh(slideshow)
    narrative = db_session.get(NarrativeStructure, slideshow.current_narrative_structure_id)
    beats = {s["slide_index"]: s["beat"] for s in narrative.structured_json["slides"]}
    assert beats == {0: "hook", 1: "reveal", 2: "cta"}
    assert narrative.ocr_result_ids_json == [
        slides[0].current_ocr_result_id,
        slides[1].current_ocr_result_id,
        slides[2].current_ocr_result_id,
    ]


def test_slide_with_no_ocr_text_is_forced_unclassifiable_not_guessed(db_session, tmp_path, monkeypatch):
    """
    The real point of this design (see the stage's own module docstring):
    a slide with no OCR text is never sent to the AI and is always
    unclassifiable, regardless of what the AI might have said if asked -
    the code guarantees this, not a prompt instruction.
    """
    slideshow, slides = _make_multi_slide_slideshow(db_session, tmp_path, ["Real headline here", ""])

    # Even if the fake AI "hallucinated" a confident beat for slide 1
    # (which was never sent to it - only slide_index 0 was in the
    # prompt), the stage must not use it.
    fake_registry = FakeAIProviderRegistry(
        text_generation_provider=FakeTextGenerationProvider(
            result={
                "slides": [{"slide_index": 0, "beat": "hook"}],
                "arc_summary": "Only one slide had real text.",
            }
        )
    )
    monkeypatch.setattr("app.slideshow_stages.narrative_structure_stage.default_registry", fake_registry)

    result = SlideshowNarrativeStructureStage().run(db_session, slideshow)

    assert result.succeeded is True
    db_session.refresh(slideshow)
    narrative = db_session.get(NarrativeStructure, slideshow.current_narrative_structure_id)
    beats = {s["slide_index"]: s["beat"] for s in narrative.structured_json["slides"]}
    assert beats == {0: "hook", 1: BEAT_UNCLASSIFIABLE}
    assert narrative.ocr_result_ids_json == [slides[0].current_ocr_result_id, None]


def test_rerun_produces_new_version_and_flips_previous(db_session, slideshow_with_slide, monkeypatch):
    slide = slideshow_with_slide.primary_slide
    _set_ocr(db_session, slide, "Some headline text")

    fake_registry = FakeAIProviderRegistry(
        text_generation_provider=FakeTextGenerationProvider(
            result={"slides": [{"slide_index": 0, "beat": "hook"}], "arc_summary": "v1"}
        )
    )
    monkeypatch.setattr("app.slideshow_stages.narrative_structure_stage.default_registry", fake_registry)
    stage = SlideshowNarrativeStructureStage()
    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slideshow_with_slide)
    first_id = slideshow_with_slide.current_narrative_structure_id

    fake_registry_v2 = FakeAIProviderRegistry(
        text_generation_provider=FakeTextGenerationProvider(
            result={"slides": [{"slide_index": 0, "beat": "cta"}], "arc_summary": "v2"}
        )
    )
    monkeypatch.setattr("app.slideshow_stages.narrative_structure_stage.default_registry", fake_registry_v2)
    stage.run(db_session, slideshow_with_slide)
    db_session.refresh(slideshow_with_slide)
    second_id = slideshow_with_slide.current_narrative_structure_id

    assert second_id != first_id
    first = db_session.get(NarrativeStructure, first_id)
    assert first.is_current is False
    assert first.structured_json["arc_summary"] == "v1"  # untouched
    second = db_session.get(NarrativeStructure, second_id)
    assert second.is_current is True
    assert second.structured_json["arc_summary"] == "v2"
