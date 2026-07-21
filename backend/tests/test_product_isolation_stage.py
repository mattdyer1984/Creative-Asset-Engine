"""
Unit tests for ProductIsolationStage (plan §13's Stage contract tests).
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.models.product_reference_image import ProductReferenceImage
from app.stages.product_isolation_stage import ISOLATION_METHOD, ProductIsolationStage
from tests.fakes import FakeAIProviderRegistry, FakeProductIsolationProvider


def test_fails_gracefully_without_a_product_assigned(db_session, creative_with_blueprint, monkeypatch):
    """creative_with_blueprint (not creative_with_product) has no product_id set."""
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = ProductIsolationStage()
    result = stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    assert result.succeeded is False
    assert "No product assigned" in result.error
    # No AnalysisRun should even be created for a prerequisite that was
    # never met - there was nothing to attempt.
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_succeeds_and_crops_reference_image(db_session, creative_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = ProductIsolationStage()
    result = stage.run(db_session, creative_with_product, creative_with_product.blueprint)

    assert result.succeeded is True

    reference_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.product_id == creative_with_product.product_id
            )
        )
    )
    assert len(reference_images) == 1
    ref = reference_images[0]
    assert ref.is_current is True
    assert ref.isolation_method == ISOLATION_METHOD
    assert ref.source_creative_id == creative_with_product.id

    analysis_run = db_session.get(AnalysisRun, ref.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "product_isolation"


def test_fails_gracefully_when_no_product_detected(db_session, creative_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=[])),
    )

    stage = ProductIsolationStage()
    result = stage.run(db_session, creative_with_product, creative_with_product.blueprint)

    assert result.succeeded is False
    assert "No product detected" in result.error

    analysis_run = db_session.scalars(select(AnalysisRun)).first()
    assert analysis_run.status == STATUS_FAILED


def test_rerun_produces_new_version_and_flips_previous(db_session, creative_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = ProductIsolationStage()
    stage.run(db_session, creative_with_product, creative_with_product.blueprint)
    stage.run(db_session, creative_with_product, creative_with_product.blueprint)

    all_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.product_id == creative_with_product.product_id
            )
        )
    )
    assert len(all_images) == 2
    current = [img for img in all_images if img.is_current]
    assert len(current) == 1  # only the most recent rerun is current


def test_failed_rerun_does_not_touch_previously_current_image(
    db_session, creative_with_product, monkeypatch
):
    """
    Directly answers: does a rerun only flip previous ProductReferenceImage
    rows to not-current AFTER the new run succeeds? Runs isolation
    successfully once, then reruns with a provider configured to fail -
    the original reference image must remain is_current=True, and the
    failed attempt must still be recorded as its own AnalysisRun.
    """
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    stage = ProductIsolationStage()
    stage.run(db_session, creative_with_product, creative_with_product.blueprint)

    original_image = db_session.scalars(
        select(ProductReferenceImage).where(
            ProductReferenceImage.product_id == creative_with_product.product_id
        )
    ).one()
    assert original_image.is_current is True

    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(
            isolation_provider=FakeProductIsolationProvider(raise_error=RuntimeError("provider down"))
        ),
    )
    result = stage.run(db_session, creative_with_product, creative_with_product.blueprint)
    assert result.succeeded is False

    db_session.refresh(original_image)
    assert original_image.is_current is True  # untouched by the failed rerun

    all_images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.product_id == creative_with_product.product_id
            )
        )
    )
    assert len(all_images) == 1  # no new (partial or otherwise) row was created

    runs = list(db_session.scalars(select(AnalysisRun)))
    assert len(runs) == 2  # the successful run + the failed rerun, both preserved
    assert runs[1].status == STATUS_FAILED
    assert "provider down" in runs[1].error


def test_multiple_crops_are_all_persisted_and_current(db_session, creative_with_product, monkeypatch):
    """If the provider detects more than one product instance, every crop should persist as current."""
    two_boxes = [
        {"x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.9, "confidence": 0.9, "notes": "left bottle"},
        {"x_min": 0.6, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.85, "notes": "right bottle"},
    ]
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=two_boxes)),
    )

    stage = ProductIsolationStage()
    result = stage.run(db_session, creative_with_product, creative_with_product.blueprint)

    assert result.succeeded is True
    images = list(
        db_session.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.product_id == creative_with_product.product_id
            )
        )
    )
    assert len(images) == 2
    assert all(img.is_current for img in images)
