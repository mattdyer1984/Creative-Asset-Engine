"""
Unit tests for Slide.current_product_appearances (plural) - Phase 6.1 of
multi per-slide product detection, see MIGRATION_PLAN.md. Mirrors
tests/test_slideshow_model.py's style for Phase 4.1's equivalent
non-breaking-addition pattern.
"""

from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.slide import Slide
from app.models.slideshow import Slideshow


def _make_slide(db_session) -> Slide:
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
    return slide


def _make_product(db_session, name: str) -> Product:
    product = Product(display_name=name)
    db_session.add(product)
    db_session.commit()
    return product


def test_current_product_appearances_is_empty_list_when_none_assigned(db_session):
    slide = _make_slide(db_session)
    assert slide.current_product_appearances == []
    # current_product_appearance (singular) unchanged - still None.
    assert slide.current_product_appearance is None


def test_current_product_appearances_returns_every_current_one(db_session):
    slide = _make_slide(db_session)
    product_a = _make_product(db_session, "A")
    product_b = _make_product(db_session, "B")

    appearance_a = ProductAppearance(slide_id=slide.id, product_id=product_a.id, is_current=True)
    appearance_b = ProductAppearance(slide_id=slide.id, product_id=product_b.id, is_current=True)
    db_session.add_all([appearance_a, appearance_b])
    db_session.commit()
    db_session.refresh(slide)

    current = slide.current_product_appearances
    assert {a.id for a in current} == {appearance_a.id, appearance_b.id}
    # Singular accessor (unchanged) still returns just the first one.
    assert slide.current_product_appearance is not None


def test_current_product_appearances_excludes_non_current_rows(db_session):
    slide = _make_slide(db_session)
    product = _make_product(db_session, "A")

    old = ProductAppearance(slide_id=slide.id, product_id=product.id, is_current=False)
    current = ProductAppearance(slide_id=slide.id, product_id=product.id, is_current=True)
    db_session.add_all([old, current])
    db_session.commit()
    db_session.refresh(slide)

    result = slide.current_product_appearances
    assert len(result) == 1
    assert result[0].id == current.id
