"""
Tests for the Phase 2.2 Slideshow/Slide/ProductAppearance backfill
(app.services.slideshow_backfill).
"""

from app.models.product_appearance import ProductAppearance
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.slideshow_backfill import backfill_slideshows


def test_backfills_slideshow_and_slide_from_creative(db_session, creative_with_blueprint):
    stats = backfill_slideshows(db_session)

    assert stats.slideshows_created == 1
    assert stats.slides_created == 1
    assert stats.product_appearances_created == 0

    slideshow = db_session.get(Slideshow, creative_with_blueprint.id)
    assert slideshow is not None
    assert slideshow.project_id == creative_with_blueprint.project_id
    assert slideshow.status == creative_with_blueprint.blueprint.status
    assert slideshow.source_references_json == creative_with_blueprint.blueprint.source_references_json

    slide = db_session.query(Slide).filter(Slide.slideshow_id == slideshow.id).one()
    assert slide.slide_index == 0
    assert slide.stored_file_path == creative_with_blueprint.stored_file_path
    assert slide.original_filename == creative_with_blueprint.original_filename
    assert slide.source_type == creative_with_blueprint.source_type


def test_backfills_product_appearance_when_product_assigned(db_session, creative_with_product):
    stats = backfill_slideshows(db_session)

    assert stats.product_appearances_created == 1

    slide = db_session.query(Slide).filter(Slide.slideshow_id == creative_with_product.id).one()
    appearance = db_session.query(ProductAppearance).filter(
        ProductAppearance.slide_id == slide.id
    ).one()
    assert appearance.product_id == creative_with_product.product_id
    assert appearance.prominence == "primary"
    assert appearance.confidence == 1.0
    assert appearance.is_current is True
    assert appearance.x_min is None  # asserted, not detected - no bounding box


def test_no_product_appearance_when_no_product_assigned(db_session, creative_with_blueprint):
    backfill_slideshows(db_session)
    assert db_session.query(ProductAppearance).count() == 0


def test_idempotent_second_run_skips_already_backfilled(db_session, creative_with_blueprint):
    first = backfill_slideshows(db_session)
    assert first.slideshows_created == 1
    assert first.skipped_already_backfilled == 0

    second = backfill_slideshows(db_session)
    assert second.slideshows_created == 0
    assert second.skipped_already_backfilled == 1

    # Still exactly one Slideshow/Slide, not duplicated by the second run.
    assert db_session.query(Slideshow).count() == 1
    assert db_session.query(Slide).count() == 1


def test_slideshow_id_reuses_creative_id(db_session, creative_with_blueprint):
    backfill_slideshows(db_session)
    slideshow = db_session.get(Slideshow, creative_with_blueprint.id)
    assert slideshow.id == creative_with_blueprint.id
