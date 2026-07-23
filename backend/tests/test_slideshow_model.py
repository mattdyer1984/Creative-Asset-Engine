"""
Unit tests for Slideshow model properties. Phase 4.1 (true multi-slide
import, see MIGRATION_PLAN.md) renamed Slideshow.slide -> primary_slide
and relaxed its guard from "raise unless exactly one Slide" to "raise
only if there are zero Slides" - these tests characterize both the
unchanged single-slide behavior and the new multi-slide behavior no
existing test previously exercised (constructing 2+ Slides on one
Slideshow wasn't possible through the API until Phase 4.2).
"""

import pytest

from app.models.slide import Slide
from app.models.slideshow import Slideshow


def test_primary_slide_returns_the_only_slide(db_session):
    slideshow = Slideshow()
    db_session.add(slideshow)
    db_session.flush()
    slide = Slide(
        slideshow_id=slideshow.id,
        slide_index=0,
        stored_file_path="/tmp/x.jpg",
        original_filename="x.jpg",
        source_type="local_file",
        source_locator="x.jpg",
    )
    db_session.add(slide)
    db_session.commit()
    db_session.refresh(slideshow)

    assert slideshow.primary_slide.id == slide.id


def test_primary_slide_returns_slide_index_zero_when_multiple_exist(db_session):
    """
    The actual new behavior Phase 4.1 introduces: previously this would
    raise (Phase 2-2.7's invariant). Constructed directly via the ORM
    since the import API can't produce a multi-slide Slideshow until
    Phase 4.2 lands.
    """
    slideshow = Slideshow()
    db_session.add(slideshow)
    db_session.flush()
    slides = [
        Slide(
            slideshow_id=slideshow.id,
            slide_index=i,
            stored_file_path=f"/tmp/{i}.jpg",
            original_filename=f"{i}.jpg",
            source_type="local_file",
            source_locator=f"{i}.jpg",
        )
        for i in range(3)
    ]
    db_session.add_all(slides)
    db_session.commit()
    db_session.refresh(slideshow)

    assert slideshow.primary_slide.id == slides[0].id
    assert slideshow.primary_slide.slide_index == 0


def test_primary_slide_raises_if_no_slides(db_session):
    slideshow = Slideshow()
    db_session.add(slideshow)
    db_session.commit()
    db_session.refresh(slideshow)

    with pytest.raises(ValueError, match="has no Slides"):
        _ = slideshow.primary_slide
