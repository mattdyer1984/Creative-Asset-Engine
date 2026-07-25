"""
Unit tests for the Phase 9.7 backfill service (see MIGRATION_PLAN.md's
"ADR: Canonical Product Reference" §11/§12). No real vision call -
FakeVisionAnalysisProvider throughout. Only the service function is
tested here - scripts/backfill_reference_scoring.py is a thin CLI
wrapper around it with no logic of its own worth duplicating coverage
for.
"""

from PIL import Image

from app.models.product import Product
from app.models.product_reference_image import ProductReferenceImage
from app.services.reference_scoring_backfill import backfill_all_products
from tests.fakes import FakeAIProviderRegistry, FakeVisionAnalysisProvider

GOOD_TIER2_RESULT = {
    "role": "front",
    "front_visible": True,
    "occluded": False,
    "brand_readable": True,
    "packaging_visible": True,
    "composition_quality": "excellent",
    "reasons": ["clean, well-lit shot"],
}


def _save_realistic_test_image(path, size=(400, 400)):
    Image.effect_noise(size, 40).convert("RGB").save(path, format="JPEG")


def _make_product_with_unscored_image(db_session, tmp_path, *, name, filename):
    product = Product(display_name=name)
    db_session.add(product)
    db_session.flush()

    path = tmp_path / filename
    _save_realistic_test_image(path)
    image = ProductReferenceImage(
        product_id=product.id, file_path=str(path), isolation_method="product_url"
    )
    db_session.add(image)
    db_session.commit()
    db_session.refresh(product)
    db_session.refresh(image)
    return product, image


def test_dry_run_reports_candidate_counts_without_any_vision_call(db_session, tmp_path, monkeypatch):
    product, _image = _make_product_with_unscored_image(
        db_session, tmp_path, name="Sunrise Orange Juice", filename="ref.jpg"
    )
    fake_vision = FakeVisionAnalysisProvider(result=GOOD_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    results = backfill_all_products(db_session, dry_run=True)

    assert len(results) == 1
    assert results[0].product_id == product.id
    assert results[0].candidate_count == 1
    assert results[0].succeeded is None
    assert fake_vision.last_prompt_spec is None  # dry-run never calls the provider


def test_live_run_scores_every_product_with_unscored_candidates(db_session, tmp_path, monkeypatch):
    product_a, image_a = _make_product_with_unscored_image(
        db_session, tmp_path, name="Sunrise Orange Juice", filename="a.jpg"
    )
    product_b, image_b = _make_product_with_unscored_image(
        db_session, tmp_path, name="Evoband", filename="b.jpg"
    )
    fake_vision = FakeVisionAnalysisProvider(result=GOOD_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    results = backfill_all_products(db_session, dry_run=False)

    assert {r.product_id for r in results} == {product_a.id, product_b.id}
    assert all(r.succeeded is True for r in results)
    db_session.refresh(image_a)
    db_session.refresh(image_b)
    assert image_a.library_status == "included"
    assert image_b.library_status == "included"


def test_product_ids_filter_scopes_to_a_single_product(db_session, tmp_path, monkeypatch):
    product_a, image_a = _make_product_with_unscored_image(
        db_session, tmp_path, name="Sunrise Orange Juice", filename="a.jpg"
    )
    _product_b, image_b = _make_product_with_unscored_image(
        db_session, tmp_path, name="Evoband", filename="b.jpg"
    )
    fake_vision = FakeVisionAnalysisProvider(result=GOOD_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    results = backfill_all_products(db_session, dry_run=False, product_ids=[product_a.id])

    assert [r.product_id for r in results] == [product_a.id]
    db_session.refresh(image_a)
    db_session.refresh(image_b)
    assert image_a.library_status == "included"
    assert image_b.library_status is None  # untouched - out of scope


def test_products_with_nothing_unscored_are_silently_skipped(db_session, tmp_path, monkeypatch):
    product, image = _make_product_with_unscored_image(
        db_session, tmp_path, name="Sunrise Orange Juice", filename="ref.jpg"
    )
    image.library_status = "included"
    image.role = "front"
    image.quality_score = 0.9
    db_session.commit()

    results = backfill_all_products(db_session, dry_run=True)

    assert results == []


def test_one_products_failure_does_not_block_another_products_success(db_session, tmp_path, monkeypatch):
    product_a, image_a = _make_product_with_unscored_image(
        db_session, tmp_path, name="Sunrise Orange Juice", filename="a.jpg"
    )
    product_b, image_b = _make_product_with_unscored_image(
        db_session, tmp_path, name="Evoband", filename="b.jpg"
    )

    calls = {"count": 0}

    class _FlakyVisionProvider:
        model = "fake-vision-model"
        provider = "openai"

        def analyze_creative(self, image_bytes, prompt_spec, response_schema, *, usage_sink=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("vision provider down")
            return GOOD_TIER2_RESULT

    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=_FlakyVisionProvider()),
    )

    results = backfill_all_products(db_session, dry_run=False)

    assert len(results) == 2
    by_product = {r.product_id: r for r in results}
    assert by_product[product_a.id].succeeded is False
    assert by_product[product_b.id].succeeded is True
    db_session.refresh(image_a)
    db_session.refresh(image_b)
    assert image_a.library_status is None  # no partial write on the failed product
    assert image_b.library_status == "included"
