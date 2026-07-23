"""
Unit tests for SlideCreativeSpecificationStage (new pipeline, Phase 2.4e,
renamed from SlideRecreationPromptStage in Phase 8.1 - see
MIGRATION_PLAN.md) - mirrors tests/test_recreation_prompt_stage.py's
coverage.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.analysis_run import ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE, STATUS_SUCCEEDED, AnalysisRun
from app.models.creative_specification import CreativeSpecification
from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.product_lock_profile import ProductLockProfile
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.creative_specification_stage import (
    SlideCreativeSpecificationStage,
    resolve_primary_appearance,
)
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import SlideProductLockProfileStage
from app.stages.execution import start_analysis_run
from tests.fakes import FakeAIProviderRegistry, FakePromptGenerationProvider, FakeVisionAnalysisProvider
from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT


def _build_prerequisites(db_session, slideshow, monkeypatch):
    """Runs Product Isolation, Product Lock Profile, and Creative Fingerprint first."""
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    SlideProductIsolationStage().run(db_session, slideshow)
    SlideProductLockProfileStage().run(db_session, slideshow)
    SlideCreativeFingerprintStage().run(db_session, slideshow)


@dataclass
class _FakeAppearance:
    """
    Minimal stand-in for ProductAppearance - resolve_primary_appearance
    (Phase 6.3) only ever reads .prominence, .created_at, and .id, so a
    real DB row isn't needed to unit-test the resolution logic itself.
    """

    id: str
    product_id: str
    prominence: str
    created_at: datetime


def test_resolve_primary_appearance_empty_list_returns_none():
    assert resolve_primary_appearance([]) is None


def test_resolve_primary_appearance_single_appearance_returns_it():
    only = _FakeAppearance("a1", "p1", "primary", datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert resolve_primary_appearance([only]) is only


def test_resolve_primary_appearance_prefers_prominence_primary_over_creation_order():
    later_but_primary = _FakeAppearance(
        "a2", "p2", "primary", datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    earlier_secondary = _FakeAppearance(
        "a1", "p1", "secondary", datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    result = resolve_primary_appearance([earlier_secondary, later_but_primary])
    assert result is later_but_primary


def test_resolve_primary_appearance_falls_back_to_earliest_created_when_none_marked_primary():
    earlier = _FakeAppearance("a1", "p1", "secondary", datetime(2026, 1, 1, tzinfo=timezone.utc))
    later = _FakeAppearance("a2", "p2", "secondary", datetime(2026, 1, 2, tzinfo=timezone.utc))
    result = resolve_primary_appearance([later, earlier])
    assert result is earlier


def test_resolve_primary_appearance_ties_among_primaries_broken_by_earliest_created():
    same_instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    earlier_primary = _FakeAppearance("a1", "p1", "primary", same_instant)
    later_primary = _FakeAppearance("a2", "p2", "primary", same_instant + timedelta(seconds=1))
    result = resolve_primary_appearance([later_primary, earlier_primary])
    assert result is earlier_primary


def test_fails_gracefully_without_a_lock_profile(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )

    result = SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No Product Lock Profile" in result.error
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_fails_gracefully_without_a_fingerprint(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    SlideProductLockProfileStage().run(db_session, slideshow_with_product)

    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )
    result = SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No Creative Fingerprint" in result.error


def test_succeeds_and_assembles_product_lock_reference(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )
    result = SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is True

    db_session.refresh(slideshow_with_product)
    spec_id = slideshow_with_product.current_creative_specification_id
    assert spec_id is not None

    spec = db_session.get(CreativeSpecification, spec_id)
    assert spec.is_current is True
    assert spec.slideshow_id == slideshow_with_product.id
    assert spec.creative_id is None

    structured = spec.structured_json
    assert structured["subject"]
    assert structured["aspect_ratio"] == "4:5"
    assert structured["product_lock_reference"]["product_lock_profile_id"] == spec.product_lock_profile_id
    assert structured["product_lock_reference"]["immutable_characteristics"] == [
        "bottle shape",
        "label design",
        "cap color",
    ]

    analysis_run = db_session.get(AnalysisRun, spec.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "creative_specification"
    assert analysis_run.slideshow_id == slideshow_with_product.id


def test_ai_is_never_asked_to_produce_ids(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)

    fake_prompt_provider = FakePromptGenerationProvider()
    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry",
        FakeAIProviderRegistry(prompt_generation_provider=fake_prompt_provider),
    )

    SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)

    assert fake_prompt_provider.last_call is not None
    assert "product_category" in fake_prompt_provider.last_call["lock_profile"]
    assert "visual_style" in fake_prompt_provider.last_call["fingerprint"]


def test_fails_gracefully_on_provider_error(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry",
        FakeAIProviderRegistry(
            prompt_generation_provider=FakePromptGenerationProvider(raise_error=RuntimeError("provider down"))
        ),
    )

    result = SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "provider down" in result.error

    db_session.refresh(slideshow_with_product)
    assert slideshow_with_product.current_creative_specification_id is None


def test_rerun_produces_new_version(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideCreativeSpecificationStage()
    stage.run(db_session, slideshow_with_product)
    db_session.refresh(slideshow_with_product)
    first_id = slideshow_with_product.current_creative_specification_id

    stage.run(db_session, slideshow_with_product)
    db_session.refresh(slideshow_with_product)
    second_id = slideshow_with_product.current_creative_specification_id

    assert second_id != first_id
    first = db_session.get(CreativeSpecification, first_id)
    assert first.is_current is False


def _create_lock_profile(db_session, product_id, structured_json):
    """
    Directly persists a current ProductLockProfile for a product, bypassing
    SlideProductLockProfileStage - that stage now rejects multi-product
    slides outright (Phase 6.2), so a two-product setup for this test has
    to build its lock profiles by hand.
    """
    analysis_run = start_analysis_run(
        db_session,
        analysis_type=ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE,
        provider="fake",
        model_name="fake",
        durable=False,
    )
    profile = ProductLockProfile(
        analysis_run_id=analysis_run.id,
        product_id=product_id,
        structured_json=structured_json,
        reference_image_ids_json=[],
    )
    db_session.add(profile)
    db_session.commit()
    return profile


def test_multi_product_slide_builds_specification_around_the_primary_appearance(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Phase 6.3: unlike Product Isolation/Lock Profile, a multi-product
    slide doesn't fail Creative Specification outright - it resolves to
    the appearance marked prominence == "primary" and builds the
    specification around that product's Lock Profile, ignoring the
    secondary one.
    """
    slide = slideshow_with_product.primary_slide
    primary_appearance = slide.current_product_appearances[0]
    assert primary_appearance.prominence == "primary"  # fixture default, asserted for clarity

    secondary_product = Product(display_name="Secondary Product")
    db_session.add(secondary_product)
    db_session.flush()
    db_session.add(
        ProductAppearance(
            slide_id=slide.id,
            product_id=secondary_product.id,
            prominence="secondary",
            confidence=1.0,
            is_current=True,
        )
    )
    db_session.commit()

    primary_profile = _create_lock_profile(
        db_session, primary_appearance.product_id, {"product_category": "primary-product"}
    )
    _create_lock_profile(db_session, secondary_product.id, {"product_category": "secondary-product"})

    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    SlideCreativeFingerprintStage().run(db_session, slideshow_with_product)

    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )
    result = SlideCreativeSpecificationStage().run(db_session, slideshow_with_product)

    assert result.succeeded is True
    db_session.refresh(slideshow_with_product)
    spec = db_session.get(CreativeSpecification, slideshow_with_product.current_creative_specification_id)
    assert spec.product_lock_profile_id == primary_profile.id
