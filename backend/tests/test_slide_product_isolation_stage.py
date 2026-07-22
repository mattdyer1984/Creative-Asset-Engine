"""
Unit tests for SlideProductIsolationStage (new pipeline, Phase 2.4a) -
mirrors tests/test_product_isolation_stage.py's coverage of the old
ProductIsolationStage.
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.models.product_reference_image import ProductReferenceImage
from app.slideshow_stages.product_isolation_stage import (
    ISOLATION_METHOD,
    SlideProductIsolationStage,
)
from tests.fakes import FakeAIProviderRegistry, FakeProductIsolationProvider


def test_fails_gracefully_without_a_product_assigned(db_session, slideshow_with_slide, monkeypatch):
    """slideshow_with_slide (not slideshow_with_product) has no ProductAppearance."""
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "No product assigned" in result.error
    # No AnalysisRun should even be created for a prerequisite that was never met.
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_succeeds_and_crops_reference_image(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is True

    slide = slideshow_with_product.slide
    reference_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.source_slide_id == slide.id
            )
        )
    )
    assert len(reference_images) == 1
    ref = reference_images[0]
    assert ref.is_current is True
    assert ref.isolation_method == ISOLATION_METHOD
    assert ref.source_slide_id == slide.id
    assert ref.source_creative_id is None  # new pipeline never writes the legacy FK

    analysis_run = db_session.get(AnalysisRun, ref.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "product_isolation"
    assert analysis_run.slide_id == slide.id


def test_fails_gracefully_when_no_product_detected(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=[])),
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No product detected" in result.error

    analysis_run = db_session.scalars(select(AnalysisRun)).first()
    assert analysis_run.status == STATUS_FAILED


def test_rerun_produces_new_version_and_flips_previous(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductIsolationStage()
    stage.run(db_session, slideshow_with_product)
    stage.run(db_session, slideshow_with_product)

    product_id = slideshow_with_product.slide.product_appearances[0].product_id
    all_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.product_id == product_id)
        )
    )
    assert len(all_images) == 2
    current = [img for img in all_images if img.is_current]
    assert len(current) == 1


def test_multiple_crops_are_all_persisted_and_current(db_session, slideshow_with_product, monkeypatch):
    two_boxes = [
        {"x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.9, "confidence": 0.9, "notes": "left bottle"},
        {"x_min": 0.6, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.85, "notes": "right bottle"},
    ]
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=two_boxes)),
    )

    stage = SlideProductIsolationStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is True
    slide = slideshow_with_product.slide
    images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(ProductReferenceImage.source_slide_id == slide.id)
        )
    )
    assert len(images) == 2
    assert all(img.is_current for img in images)
