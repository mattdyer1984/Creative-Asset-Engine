"""
`_overlay_text` - the OCR read the specification stage was missing.

`ocr` had been a declared dependency of that stage for its whole life and
nothing read it, so the specification never knew how much text the original
carried and wrote a full three-part advert for a creative with one caption.

The None/[] distinction is the part worth guarding: they mean different
things and collapsing them silently suppresses every overlay.
"""

from __future__ import annotations

from app.models.ocr_result import OCRResult
from app.slideshow_stages.creative_specification_stage import _overlay_text


def _ocr(db, slide_id, blocks, *, is_current=True):
    db.add(OCRResult(
        slide_id=slide_id, raw_text="", structured_blocks_json=blocks,
        analysis_run_id=f"run-{slide_id}-{int(is_current)}", is_current=is_current,
    ))
    db.flush()


def test_only_overlay_surface_blocks_are_returned(db_session):
    """
    Text printed on a book cover is part of the photographed scene, not
    marketing copy the recreation should reproduce as an overlay.
    """
    _ocr(db_session, "slide-1", [
        {"text": "All 5 books for the price of 1 right now", "surface": "overlay"},
        {"text": "Atomic Habits", "surface": "physical"},
        {"text": "James Clear", "surface": "physical"},
    ])
    assert _overlay_text(db_session, "slide-1") == [
        "All 5 books for the price of 1 right now"
    ]


def test_no_ocr_result_returns_none_not_empty(db_session):
    """
    None means "not known - leave the prompt as it was". An empty list would
    tell the model the original has no overlay text and suppress all of it.
    """
    assert _overlay_text(db_session, "slide-missing") is None


def test_a_creative_with_no_overlay_text_returns_an_empty_list(db_session):
    """Genuinely no overlay text - different from not having looked."""
    _ocr(db_session, "slide-2", [{"text": "Atomic Habits", "surface": "physical"}])
    assert _overlay_text(db_session, "slide-2") == []


def test_blank_and_whitespace_blocks_are_dropped(db_session):
    _ocr(db_session, "slide-3", [
        {"text": "  ", "surface": "overlay"},
        {"text": "", "surface": "overlay"},
        {"text": "  Real copy  ", "surface": "overlay"},
    ])
    assert _overlay_text(db_session, "slide-3") == ["Real copy"]


def test_a_block_with_no_surface_is_not_assumed_to_be_an_overlay(db_session):
    """Absent is not 'overlay' - OCR's own default is 'physical'."""
    _ocr(db_session, "slide-4", [{"text": "Ambiguous"}])
    assert _overlay_text(db_session, "slide-4") == []


def test_an_empty_blocks_list_is_an_empty_inventory(db_session):
    _ocr(db_session, "slide-5", [])
    assert _overlay_text(db_session, "slide-5") == []


def test_multiple_overlay_blocks_keep_their_order(db_session):
    _ocr(db_session, "slide-6", [
        {"text": "Hook", "surface": "overlay"},
        {"text": "Offer", "surface": "physical"},
        {"text": "Close", "surface": "overlay"},
    ])
    assert _overlay_text(db_session, "slide-6") == ["Hook", "Close"]


def test_a_superseded_ocr_row_is_ignored(db_session):
    """
    Re-analysing leaves the old row behind. An unfiltered `.first()` would
    let it decide what the specification believes the original says.
    """
    _ocr(db_session, "slide-7", [
        {"text": "Stale headline nobody wrote", "surface": "overlay"},
    ], is_current=False)
    _ocr(db_session, "slide-7", [
        {"text": "All 5 books for the price of 1 right now", "surface": "overlay"},
    ], is_current=True)
    assert _overlay_text(db_session, "slide-7") == [
        "All 5 books for the price of 1 right now"
    ]
