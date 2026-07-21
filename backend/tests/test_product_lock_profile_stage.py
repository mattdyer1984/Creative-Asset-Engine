"""
Unit tests for ProductLockProfileStage (plan §13's Stage contract tests).
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.product_lock_profile import ProductLockProfile
from app.stages.product_lock_profile_stage import ProductLockProfileStage
from tests.fakes import FakeAIProviderRegistry


def test_fails_gracefully_without_a_product_assigned(db_session, creative_with_blueprint, monkeypatch):
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = ProductLockProfileStage()
    result = stage.run(db_session, creative_with_blueprint, creative_with_blueprint.blueprint)

    assert result.succeeded is False
    assert "No product assigned" in result.error


def test_succeeds_without_reference_images_yet(db_session, creative_with_product, monkeypatch):
    """
    Product Lock Profile Stage run standalone, before Product Isolation
    has ever produced a reference image - should still succeed (plan
    note: not a hard prerequisite), with an empty reference snapshot.
    """
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = ProductLockProfileStage()
    result = stage.run(db_session, creative_with_product, creative_with_product.blueprint)

    assert result.succeeded is True

    db_session.refresh(creative_with_product.blueprint)
    profile_id = creative_with_product.blueprint.current_product_lock_profile_id
    assert profile_id is not None

    profile = db_session.get(ProductLockProfile, profile_id)
    assert profile.is_current is True
    assert profile.reference_image_ids_json == []

    structured = profile.structured_json
    assert structured["product_category"] == "beverage"
    assert structured["branding"]["brand_name"] == "Sunrise"

    analysis_run = db_session.get(AnalysisRun, profile.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "product_lock_profile"


def test_snapshots_current_reference_images(db_session, creative_with_product, monkeypatch):
    """Running Product Isolation first, then Product Lock Profile, snapshots the resulting image id."""
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    from app.stages.product_isolation_stage import ProductIsolationStage

    ProductIsolationStage().run(db_session, creative_with_product, creative_with_product.blueprint)
    ProductLockProfileStage().run(db_session, creative_with_product, creative_with_product.blueprint)

    db_session.refresh(creative_with_product.blueprint)
    profile = db_session.get(
        ProductLockProfile, creative_with_product.blueprint.current_product_lock_profile_id
    )
    snapshotted_ids = profile.reference_image_ids_json
    assert len(snapshotted_ids) == 1


def test_snapshots_all_current_images_when_isolation_produces_multiple_crops(
    db_session, creative_with_product, monkeypatch
):
    """
    Directly answers: if Product Isolation detects more than one product
    instance and produces multiple ProductReferenceImage rows, does the
    Product Lock Profile stage's reference_image_ids_json snapshot
    include ALL of them, not just the first? The snapshot is built from a
    full query result (list), not a single row - this proves it in
    practice, not just by reading the query code.

    Note: this snapshot only records *which* reference images were
    current at generation time for traceability - the actual AI-generated
    description (structured_json) is produced from the Creative's single
    full original image, not by analyzing each crop individually. That's
    an intentional design choice (documented in this stage's module
    docstring: reference crops are reusable assets for future image
    generation, not additional analysis input), not an oversight.
    """
    from app.stages.product_isolation_stage import ProductIsolationStage
    from tests.fakes import FakeProductIsolationProvider

    two_boxes = [
        {"x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.9, "confidence": 0.9, "notes": "left"},
        {"x_min": 0.6, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.85, "notes": "right"},
    ]
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=two_boxes)),
    )
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    ProductIsolationStage().run(db_session, creative_with_product, creative_with_product.blueprint)
    ProductLockProfileStage().run(db_session, creative_with_product, creative_with_product.blueprint)

    db_session.refresh(creative_with_product.blueprint)
    profile = db_session.get(
        ProductLockProfile, creative_with_product.blueprint.current_product_lock_profile_id
    )
    snapshotted_ids = profile.reference_image_ids_json
    assert len(snapshotted_ids) == 2


def test_rerun_produces_new_version(db_session, creative_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = ProductLockProfileStage()
    stage.run(db_session, creative_with_product, creative_with_product.blueprint)
    db_session.refresh(creative_with_product.blueprint)
    first_id = creative_with_product.blueprint.current_product_lock_profile_id

    stage.run(db_session, creative_with_product, creative_with_product.blueprint)
    db_session.refresh(creative_with_product.blueprint)
    second_id = creative_with_product.blueprint.current_product_lock_profile_id

    assert second_id != first_id

    all_profiles = list(
        db_session.scalars(
            select(ProductLockProfile).where(
                ProductLockProfile.product_id == creative_with_product.product_id
            )
        )
    )
    assert len(all_profiles) == 2
    first = db_session.get(ProductLockProfile, first_id)
    assert first.is_current is False
