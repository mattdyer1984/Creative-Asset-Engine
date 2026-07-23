"""
Unit tests for the Reference Scoring Stage (Phase 9.2 of Product Lock v2,
see MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §4). No real
vision call - FakeVisionAnalysisProvider throughout.
"""

from PIL import Image
from sqlalchemy import select

from app.models.product import Product
from app.models.product_reference_image import ProductReferenceImage
from app.services.reference_acquisition import get_candidate_reference_images, get_unscored_candidates
from app.services.reference_scoring_stage import run_reference_scoring
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

POOR_TIER2_RESULT = {
    "role": "other",
    "front_visible": False,
    "occluded": True,
    "brand_readable": False,
    "packaging_visible": False,
    "composition_quality": "poor",
    "reasons": ["mostly out of frame"],
}


def _save_realistic_test_image(path, size):
    """
    A flat solid-color image (PIL's usual test-fixture shortcut) JPEG-
    compresses to ~3KB regardless of dimensions - well under any
    sharpness-proxy floor a real photo would clear, and would make every
    scoring test either exercise the Tier 1 floor by accident or need an
    unrealistically low MIN_FILE_SIZE_BYTES. Noise-based fill produces a
    file size in the same ballpark as a real product photo instead.
    """
    Image.effect_noise(size, 40).convert("RGB").save(path, format="JPEG")


def _make_product_with_reference_image(db_session, tmp_path, *, size=(400, 400), filename="ref.jpg"):
    product = Product(display_name="Sunrise Orange Juice")
    db_session.add(product)
    db_session.flush()

    image_path = tmp_path / filename
    _save_realistic_test_image(image_path, size)

    reference_image = ProductReferenceImage(
        product_id=product.id,
        file_path=str(image_path),
        isolation_method="product_url",
    )
    db_session.add(reference_image)
    db_session.commit()
    db_session.refresh(product)
    db_session.refresh(reference_image)
    return product, reference_image


def test_acquisition_returns_every_current_candidate(db_session, tmp_path):
    product, reference_image = _make_product_with_reference_image(db_session, tmp_path)

    candidates = get_candidate_reference_images(db_session, product.id)

    assert [c.id for c in candidates] == [reference_image.id]


def test_unscored_candidates_excludes_already_scored_rows(db_session, tmp_path):
    product, reference_image = _make_product_with_reference_image(db_session, tmp_path)
    reference_image.library_status = "included"
    db_session.commit()

    assert get_unscored_candidates(db_session, product.id) == []


def test_tier1_rejects_a_too_small_image_without_a_vision_call(db_session, tmp_path, monkeypatch):
    product, reference_image = _make_product_with_reference_image(db_session, tmp_path, size=(50, 50))
    fake_vision = FakeVisionAnalysisProvider(result=GOOD_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = run_reference_scoring(db_session, product.id)

    assert result.succeeded is True
    db_session.refresh(reference_image)
    assert reference_image.library_status == "rejected"
    assert reference_image.role is None
    assert fake_vision.last_prompt_spec is None  # never called - Tier 1 floor caught it first
    assert any("dimension" in reason for reason in reference_image.quality_reasons_json)


def test_high_quality_candidate_is_included_with_role_and_score(db_session, tmp_path, monkeypatch):
    product, reference_image = _make_product_with_reference_image(db_session, tmp_path)
    fake_vision = FakeVisionAnalysisProvider(result=GOOD_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = run_reference_scoring(db_session, product.id)

    assert result.succeeded is True
    db_session.refresh(reference_image)
    assert reference_image.library_status == "included"
    assert reference_image.role == "front"
    assert reference_image.quality_score is not None
    assert reference_image.quality_score >= 0.5
    assert "role: front" in reference_image.quality_reasons_json


def test_low_quality_tier2_result_is_rejected(db_session, tmp_path, monkeypatch):
    product, reference_image = _make_product_with_reference_image(db_session, tmp_path)
    fake_vision = FakeVisionAnalysisProvider(result=POOR_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = run_reference_scoring(db_session, product.id)

    assert result.succeeded is True
    db_session.refresh(reference_image)
    assert reference_image.library_status == "rejected"
    # Still classified and scored, not left blank - a low score is a real,
    # recorded judgment, not the same as "never got a Tier 2 call."
    assert reference_image.role == "other"
    assert reference_image.quality_score < 0.5


def test_already_scored_candidates_are_never_rescored(db_session, tmp_path, monkeypatch):
    product, reference_image = _make_product_with_reference_image(db_session, tmp_path)
    reference_image.library_status = "included"
    reference_image.role = "hero"
    reference_image.quality_score = 0.9
    db_session.commit()

    fake_vision = FakeVisionAnalysisProvider(result=POOR_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = run_reference_scoring(db_session, product.id)

    assert result.succeeded is True
    assert fake_vision.last_prompt_spec is None
    db_session.refresh(reference_image)
    assert reference_image.role == "hero"
    assert reference_image.quality_score == 0.9


def test_fails_gracefully_on_provider_error(db_session, tmp_path, monkeypatch):
    product, reference_image = _make_product_with_reference_image(db_session, tmp_path)
    fake_vision = FakeVisionAnalysisProvider(raise_error=RuntimeError("vision provider down"))
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = run_reference_scoring(db_session, product.id)

    assert result.succeeded is False
    assert "vision provider down" in result.error
    db_session.refresh(reference_image)
    assert reference_image.library_status is None  # no partial write on failure


def test_multiple_candidates_can_end_up_included_in_the_same_role(db_session, tmp_path, monkeypatch):
    """Library membership isn't one-per-role - the ADR's own explicit design point."""
    product = Product(display_name="Sunrise Orange Juice")
    db_session.add(product)
    db_session.flush()

    images = []
    for i in range(2):
        path = tmp_path / f"ref-{i}.jpg"
        _save_realistic_test_image(path, (400, 400))
        image = ProductReferenceImage(
            product_id=product.id, file_path=str(path), isolation_method="product_url"
        )
        db_session.add(image)
        images.append(image)
    db_session.commit()

    fake_vision = FakeVisionAnalysisProvider(result=GOOD_TIER2_RESULT)
    monkeypatch.setattr(
        "app.services.reference_scoring_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    result = run_reference_scoring(db_session, product.id)

    assert result.succeeded is True
    included = db_session.scalars(
        select(ProductReferenceImage).where(
            ProductReferenceImage.product_id == product.id,
            ProductReferenceImage.library_status == "included",
        )
    ).all()
    assert len(included) == 2
    assert all(image.role == "front" for image in included)
