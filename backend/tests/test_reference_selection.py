"""
Unit tests for app.services.reference_selection (Phase 9.3 of Product
Lock v2, see MIGRATION_PLAN.md's "ADR: Canonical Product Reference"
§6). No AI provider involved - the classical role-keyword path needs
none, matching the ADR's own "prove the classical path first" design.
"""

from app.ai_providers.base import ProviderCapabilities
from app.models.generation_reference_set_image import GenerationReferenceSetImage
from app.models.product import Product
from app.models.product_reference_image import ProductReferenceImage
from app.services.reference_selection import select_reference_images

_CAPABILITIES = ProviderCapabilities(
    supports_reference_images=True,
    max_reference_images=3,
    supports_masking=True,
    supports_inpainting=True,
    supported_resolutions=["1024x1024"],
)


def _make_product(db_session) -> Product:
    product = Product(display_name="Sunrise Orange Juice")
    db_session.add(product)
    db_session.flush()
    return product


def _make_reference_image(db_session, product_id, *, role, library_status, quality_score, filename):
    image = ProductReferenceImage(
        product_id=product_id,
        file_path=f"/data/storage/{filename}",
        isolation_method="product_url",
        role=role,
        library_status=library_status,
        quality_score=quality_score,
    )
    db_session.add(image)
    return image


def test_returns_none_when_the_library_is_empty(db_session):
    product = _make_product(db_session)
    db_session.commit()

    result = select_reference_images(db_session, product.id, {}, _CAPABILITIES)

    assert result is None


def test_returns_none_when_no_images_are_included(db_session):
    product = _make_product(db_session)
    _make_reference_image(
        db_session, product.id, role="front", library_status="rejected", quality_score=0.1, filename="a.jpg"
    )
    db_session.commit()

    result = select_reference_images(db_session, product.id, {}, _CAPABILITIES)

    assert result is None


def test_role_keyword_match_prefers_the_matching_role(db_session):
    product = _make_product(db_session)
    front = _make_reference_image(
        db_session, product.id, role="front", library_status="included", quality_score=0.5, filename="front.jpg"
    )
    forty_five = _make_reference_image(
        db_session,
        product.id,
        role="45_degree",
        library_status="included",
        quality_score=0.5,
        filename="45.jpg",
    )
    db_session.commit()

    creative_specification = {"composition": "45-degree product shot", "camera_and_perspective": ""}
    generation_reference_set = select_reference_images(
        db_session, product.id, creative_specification, _CAPABILITIES
    )

    assert generation_reference_set is not None
    members = (
        db_session.query(GenerationReferenceSetImage)
        .filter(GenerationReferenceSetImage.generation_reference_set_id == generation_reference_set.id)
        .order_by(GenerationReferenceSetImage.rank)
        .all()
    )
    assert [m.product_reference_image_id for m in members][0] == forty_five.id
    assert front.id in [m.product_reference_image_id for m in members]


def test_falls_back_to_quality_ranking_when_no_role_matches(db_session):
    product = _make_product(db_session)
    low = _make_reference_image(
        db_session, product.id, role="side", library_status="included", quality_score=0.3, filename="low.jpg"
    )
    high = _make_reference_image(
        db_session, product.id, role="side", library_status="included", quality_score=0.9, filename="high.jpg"
    )
    db_session.commit()

    generation_reference_set = select_reference_images(
        db_session, product.id, {"composition": "nothing role-related here"}, _CAPABILITIES
    )

    members = (
        db_session.query(GenerationReferenceSetImage)
        .filter(GenerationReferenceSetImage.generation_reference_set_id == generation_reference_set.id)
        .order_by(GenerationReferenceSetImage.rank)
        .all()
    )
    ordered_ids = [m.product_reference_image_id for m in members]
    assert ordered_ids.index(high.id) < ordered_ids.index(low.id)


def test_selection_is_capped_by_provider_max_reference_images(db_session):
    product = _make_product(db_session)
    for i in range(5):
        _make_reference_image(
            db_session,
            product.id,
            role="front",
            library_status="included",
            quality_score=0.5 + i * 0.01,
            filename=f"ref-{i}.jpg",
        )
    db_session.commit()

    narrow_capabilities = ProviderCapabilities(
        supports_reference_images=True,
        max_reference_images=2,
        supports_masking=False,
        supports_inpainting=False,
        supported_resolutions=["1024x1024"],
    )
    generation_reference_set = select_reference_images(db_session, product.id, {}, narrow_capabilities)

    members = (
        db_session.query(GenerationReferenceSetImage)
        .filter(GenerationReferenceSetImage.generation_reference_set_id == generation_reference_set.id)
        .all()
    )
    assert len(members) == 2


def test_selected_rows_carry_product_id_and_snapshotted_role(db_session):
    product = _make_product(db_session)
    image = _make_reference_image(
        db_session, product.id, role="hero", library_status="included", quality_score=0.9, filename="hero.jpg"
    )
    db_session.commit()

    generation_reference_set = select_reference_images(db_session, product.id, {}, _CAPABILITIES)

    member = (
        db_session.query(GenerationReferenceSetImage)
        .filter(GenerationReferenceSetImage.generation_reference_set_id == generation_reference_set.id)
        .one()
    )
    assert member.product_id == product.id
    assert member.product_reference_image_id == image.id
    assert member.role == "hero"


def test_generation_reference_set_starts_unlinked_to_any_generated_image(db_session):
    product = _make_product(db_session)
    _make_reference_image(
        db_session, product.id, role="front", library_status="included", quality_score=0.9, filename="a.jpg"
    )
    db_session.commit()

    generation_reference_set = select_reference_images(db_session, product.id, {}, _CAPABILITIES)

    assert generation_reference_set.generated_image_id is None
    assert generation_reference_set.analysis_run_id is None
    assert generation_reference_set.selection_method_json["method"] == "classical_role_keyword_match"
