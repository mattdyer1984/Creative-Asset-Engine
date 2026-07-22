"""
Unit tests for app.services.background_execution (Phase 3.1 - additive
infrastructure, not yet wired into any route). Mirrors
tests/test_slideshow_orchestrator.py's coverage, but goes through the
background wrapper functions instead of SlideshowOrchestrator directly,
to prove the wrapper's own session-handling doesn't change behavior.
"""

from app.models.slideshow import STATUS_FAILED, STATUS_READY
from app.services.background_execution import (
    run_pipeline_in_background,
    run_stage_in_background,
)
from tests.fakes import FakeAIProviderRegistry, FakeOCRProvider


def test_run_pipeline_in_background_succeeds(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    run_pipeline_in_background(slideshow_with_slide.id)

    db_session.refresh(slideshow_with_slide)
    # run_pipeline_in_background uses the real default_slideshow_orchestrator
    # (all 6 stages), and slideshow_with_slide has no product assigned, so
    # the pipeline runs OCR (succeeds) then fails cleanly at Product
    # Isolation's "no product assigned" precondition check - before it
    # would ever call a real AI provider. What matters for this test is
    # that OCR's write, made through the background wrapper's own
    # session, is visible from db_session (same underlying test DB) -
    # proving the two sessions share state correctly.
    assert slideshow_with_slide.primary_slide.current_ocr_result_id is not None
    assert slideshow_with_slide.status == STATUS_FAILED
    assert slideshow_with_slide.last_failed_stage == "product_isolation"


def test_run_pipeline_in_background_unknown_slideshow_is_a_no_op(db_session):
    # Must not raise - the router will have already 404'd before scheduling
    # this; a race where the row disappears between scheduling and running
    # should degrade silently, not crash the background task.
    run_pipeline_in_background("does-not-exist")


def test_run_stage_in_background_reruns_single_stage(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    run_stage_in_background(slideshow_with_slide.id, "ocr")

    db_session.refresh(slideshow_with_slide)
    assert slideshow_with_slide.status == STATUS_READY
    assert slideshow_with_slide.primary_slide.current_ocr_result_id is not None


def test_run_stage_in_background_marks_failed_on_provider_error(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.ocr_stage.default_registry",
        FakeAIProviderRegistry(ocr_provider=FakeOCRProvider(raise_error=RuntimeError("boom"))),
    )

    run_stage_in_background(slideshow_with_slide.id, "ocr")

    db_session.refresh(slideshow_with_slide)
    assert slideshow_with_slide.status == STATUS_FAILED


def test_run_stage_in_background_unknown_slideshow_is_a_no_op(db_session):
    run_stage_in_background("does-not-exist", "ocr")


def test_background_session_is_independent_of_the_test_session(db_session, slideshow_with_slide, monkeypatch):
    """
    The whole point of app.db.SessionLocal being monkeypatched (see
    conftest.py's db_session fixture) is that background_execution opens
    its OWN Session against the same test database - not literally the
    same Session object as db_session. Proven by forcing the Slide into
    db_session's identity map BEFORE the background run, then showing its
    cached attribute is untouched by the background session's commit
    until an explicit refresh (a fresh, not-yet-loaded access would just
    query current DB state either way, which wouldn't prove anything).
    """
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    slide = slideshow_with_slide.primary_slide
    assert slide.current_ocr_result_id is None

    run_stage_in_background(slideshow_with_slide.id, "ocr")

    # Still the pre-background-run value: if this were the same Session
    # object as the one background_execution used, it would already
    # reflect the new value here, with no refresh needed.
    assert slide.current_ocr_result_id is None

    db_session.refresh(slide)
    assert slide.current_ocr_result_id is not None
