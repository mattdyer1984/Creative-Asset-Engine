"""
Unit tests for SlideProductLockProfileStage (new pipeline, Phase 2.4b) -
mirrors tests/test_product_lock_profile_stage.py's coverage.
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.product_lock_profile import ProductLockProfile
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import (
    _MULTI_PRODUCT_ERROR,
    PRODUCT_LOCK_PROFILE_PROMPT,
    PRODUCT_LOCK_PROFILE_SCHEMA,
    SlideProductLockProfileStage,
)
from tests.fakes import FakeAIProviderRegistry, FakeProductIsolationProvider


def _add_second_current_appearance(db_session, slideshow_with_product):
    """Mirrors tests/test_slide_product_isolation_stage.py's helper of the same name."""
    second_product = Product(display_name="Second Product")
    db_session.add(second_product)
    db_session.flush()

    slide = slideshow_with_product.primary_slide
    db_session.add(
        ProductAppearance(
            slide_id=slide.id,
            product_id=second_product.id,
            prominence="secondary",
            confidence=1.0,
            is_current=True,
        )
    )
    db_session.commit()


def test_prompt_and_schema_warn_against_photo_overlay_text():
    """
    Real bug (see MIGRATION_PLAN.md): labels_and_text previously picked
    up text overlaid onto the source photo by whoever posted it (a
    TikTok caption), not just text physically printed on the product's
    own packaging - both the prompt and the schema's field description
    must tell the model to exclude the former.
    """
    assert "overlaid" in PRODUCT_LOCK_PROFILE_PROMPT
    assert "caption" in PRODUCT_LOCK_PROFILE_PROMPT

    labels_description = PRODUCT_LOCK_PROFILE_SCHEMA["properties"]["labels_and_text"]["description"]
    assert "overlaid" in labels_description
    assert "caption" in labels_description
    assert "watermark" in labels_description


def test_requests_the_gemini_vision_provider(db_session, slideshow_with_product, monkeypatch):
    """Real-world-driven cost/quality change (see MIGRATION_PLAN.md)."""
    fake_registry = FakeAIProviderRegistry()
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", fake_registry
    )

    SlideProductLockProfileStage().run(db_session, slideshow_with_product)

    assert fake_registry.vision_calls == ["gemini"]


def test_fails_gracefully_without_a_product_assigned(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductLockProfileStage()
    result = stage.run(db_session, slideshow_with_slide)

    assert result.succeeded is False
    assert "No product assigned" in result.error


def test_succeeds_without_reference_images_yet(db_session, slideshow_with_product, monkeypatch):
    """
    Run standalone, before Product Isolation has ever produced a
    reference image - should still succeed, with an empty reference
    snapshot.
    """
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductLockProfileStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is True

    product_id = slideshow_with_product.primary_slide.product_appearances[0].product_id
    profile = db_session.scalars(
        select(ProductLockProfile).where(ProductLockProfile.product_id == product_id)
    ).one()
    assert profile.is_current is True
    assert profile.reference_image_ids_json == []

    structured = profile.structured_json
    assert structured["product_category"] == "beverage"
    assert structured["branding"]["brand_name"] == "Sunrise"

    analysis_run = db_session.get(AnalysisRun, profile.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "product_lock_profile"
    assert analysis_run.slide_id == slideshow_with_product.primary_slide.id


def test_snapshots_current_reference_images(db_session, slideshow_with_product, monkeypatch):
    """Running Product Isolation first, then Product Lock Profile, snapshots the resulting image id."""
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    SlideProductIsolationStage().run(db_session, slideshow_with_product)
    SlideProductLockProfileStage().run(db_session, slideshow_with_product)

    product_id = slideshow_with_product.primary_slide.product_appearances[0].product_id
    profile = db_session.scalars(
        select(ProductLockProfile).where(ProductLockProfile.product_id == product_id)
    ).first()
    assert len(profile.reference_image_ids_json) == 1


def test_snapshots_all_current_images_when_isolation_produces_multiple_crops(
    db_session, slideshow_with_product, monkeypatch
):
    two_boxes = [
        {"x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.9, "confidence": 0.9, "notes": "left"},
        {"x_min": 0.6, "y_min": 0.1, "x_max": 0.9, "y_max": 0.9, "confidence": 0.85, "notes": "right"},
    ]
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry",
        FakeAIProviderRegistry(isolation_provider=FakeProductIsolationProvider(bounding_boxes=two_boxes)),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    SlideProductIsolationStage().run(db_session, slideshow_with_product)
    SlideProductLockProfileStage().run(db_session, slideshow_with_product)

    product_id = slideshow_with_product.primary_slide.product_appearances[0].product_id
    profile = db_session.scalars(
        select(ProductLockProfile).where(ProductLockProfile.product_id == product_id)
    ).first()
    assert len(profile.reference_image_ids_json) == 2


def test_rerun_produces_new_version(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideProductLockProfileStage()
    stage.run(db_session, slideshow_with_product)
    stage.run(db_session, slideshow_with_product)

    product_id = slideshow_with_product.primary_slide.product_appearances[0].product_id
    all_profiles = list(
        db_session.scalars(
            select(ProductLockProfile).where(ProductLockProfile.product_id == product_id)
        )
    )
    assert len(all_profiles) == 2
    current = [p for p in all_profiles if p.is_current]
    assert len(current) == 1


def test_no_current_product_lock_profile_pointer_on_slide_or_slideshow(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Deliberate design check: unlike the old CreativeBlueprint (which had
    current_product_lock_profile_id and produced the product-scoped
    currency bug), neither Slide nor Slideshow has any such pointer -
    ProductLockProfile's currency is purely is_current scoped to
    product_id. This test exists so that regressing this design decision
    (re-adding such a pointer) breaks loudly.
    """
    assert not hasattr(slideshow_with_product.primary_slide, "current_product_lock_profile_id")
    assert not hasattr(slideshow_with_product, "current_product_lock_profile_id")


def test_fails_clearly_with_multiple_distinct_products_assigned(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Phase 6.2: a slide with 2+ distinct current products fails with an
    explicit, honest error rather than silently generating the same
    profile twice under two different product_ids (see
    MIGRATION_PLAN.md's Phase 6.2 plan revision for why looping wasn't
    safe to implement).
    """
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    _add_second_current_appearance(db_session, slideshow_with_product)

    stage = SlideProductLockProfileStage()
    result = stage.run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert result.error == _MULTI_PRODUCT_ERROR
    assert db_session.scalars(select(AnalysisRun)).first() is None
