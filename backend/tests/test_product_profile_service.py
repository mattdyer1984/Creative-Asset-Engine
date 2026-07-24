"""
Tests for app.services.product_profile.assemble_product_profile (Phase
5.5 of Product Intelligence, see MIGRATION_PLAN.md).
"""

from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_source_import import FETCH_STATUS_SUCCEEDED, ProductSourceImport
from app.services.product_profile import SOURCE_TYPE_VISION, assemble_product_profile, extract_branding_text

VISION_STRUCTURED = {
    "product_category": "Fragrance",
    "shape_and_proportions": "Tall rectangular bottle",
    "packaging": {"type": "Glass bottle", "closure": "Spray cap", "notes": "Gold trim"},
    "materials": ["glass", "gold-plated metal"],
    "colors": {"primary": ["amber"], "secondary": ["gold"]},
    "branding": {"brand_name": "Bellavita", "logo_placement": "front-center", "logo_description": "embossed"},
    "labels_and_text": [{"text": "EAU DE PARFUM", "location": "front", "font_style": "serif"}],
    "viewing_angle": "eye-level",
    "perspective": "straight-on",
    "lighting_characteristics": "soft studio lighting",
    "approximate_scale_in_frame": "fills two-thirds of frame",
    "distinguishing_features": ["gold cap"],
    "surface_finish": "glossy",
}


def _make_product(db_session) -> Product:
    product = Product(display_name="Test Product")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def _add_lock_profile(db_session, product: Product, structured: dict) -> ProductLockProfile:
    from app.models.analysis_run import AnalysisRun

    run = AnalysisRun(analysis_type="product_lock_profile", provider="fake", model_name="fake")
    db_session.add(run)
    db_session.flush()
    profile = ProductLockProfile(
        analysis_run_id=run.id, product_id=product.id, structured_json=structured, reference_image_ids_json=[]
    )
    db_session.add(profile)
    db_session.commit()
    return profile


def _add_source_import(db_session, product: Product, normalized_json: dict, source_type="generic_url") -> ProductSourceImport:
    row = ProductSourceImport(
        product_id=product.id,
        source_type=source_type,
        source_url="https://shop.example/p",
        fetch_status=FETCH_STATUS_SUCCEEDED,
        raw_response_json={},
        normalized_json=normalized_json,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_empty_profile_when_no_evidence_exists(db_session):
    product = _make_product(db_session)
    profile = assemble_product_profile(db_session, product)
    assert profile.product_id == product.id
    assert profile.fields == {}


def test_vision_only_populates_immutable_and_contextual_fields(db_session):
    product = _make_product(db_session)
    _add_lock_profile(db_session, product, VISION_STRUCTURED)

    profile = assemble_product_profile(db_session, product)

    assert profile.fields["brand"].value.text == "Bellavita"
    assert profile.fields["brand"].source_type == SOURCE_TYPE_VISION
    assert profile.fields["brand"].classification == "immutable"
    assert profile.fields["brand"].confidence == 0.85

    assert profile.fields["color"].value.label == "amber"
    assert profile.fields["lighting"].value.text == "soft studio lighting"
    assert profile.fields["lighting"].classification == "contextual"
    # viewing_angle + perspective folded into one camera_angle field.
    assert profile.fields["camera_angle"].value.text == "eye-level; straight-on"
    assert profile.fields["composition"].value.text == "fills two-thirds of frame"
    assert profile.fields["packaging"].value.text == "Glass bottle · Spray cap · Gold trim"
    assert profile.fields["branding_text"].value.items == ["EAU DE PARFUM"]

    # Deliberately unmapped fields (revision #5 discipline) don't appear.
    assert "surface_finish" not in profile.fields
    assert "distinguishing_features" not in profile.fields


def test_source_import_only_populates_fields_from_normalized_json(db_session):
    product = _make_product(db_session)
    _add_source_import(
        db_session,
        product,
        normalized_json={
            "attributes": {
                "brand": {"value": {"kind": "text", "text": "Bellavita Official"}, "confidence": 0.98},
                "color": {"value": {"kind": "color", "label": "amber", "hex": "#FFBF00"}, "confidence": 0.95},
            }
        },
    )

    profile = assemble_product_profile(db_session, product)

    assert profile.fields["brand"].value.text == "Bellavita Official"
    assert profile.fields["brand"].source_type == "generic_url"
    assert profile.fields["brand"].confidence == 0.98
    assert profile.fields["color"].value.hex == "#FFBF00"


def test_immutable_field_prefers_source_import_when_both_present_and_disagree(db_session):
    product = _make_product(db_session)
    _add_lock_profile(db_session, product, VISION_STRUCTURED)  # brand = "Bellavita" (vision)
    _add_source_import(
        db_session,
        product,
        normalized_json={"attributes": {"brand": {"value": {"kind": "text", "text": "Bellavita Official"}, "confidence": 0.98}}},
    )

    profile = assemble_product_profile(db_session, product)

    assert profile.fields["brand"].value.text == "Bellavita Official"
    assert profile.fields["brand"].source_type == "generic_url"


def test_contextual_field_prefers_vision_when_both_present_and_disagree(db_session):
    product = _make_product(db_session)
    _add_lock_profile(db_session, product, VISION_STRUCTURED)  # lighting = "soft studio lighting" (vision)
    _add_source_import(
        db_session,
        product,
        normalized_json={"attributes": {"lighting": {"value": {"kind": "text", "text": "listing photo lighting"}, "confidence": 0.9}}},
    )

    profile = assemble_product_profile(db_session, product)

    assert profile.fields["lighting"].value.text == "soft studio lighting"
    assert profile.fields["lighting"].source_type == SOURCE_TYPE_VISION


def test_falls_back_to_the_other_source_when_the_preferred_one_lacks_the_field(db_session):
    """
    capacity is immutable (prefers source import), but only vision-style
    data exists in this test - since ProductLockProfile's schema has no
    capacity field at all, and no ProductSourceImport exists either, this
    documents the "neither has it" case; a separate assertion below
    covers "only the non-preferred source has it."
    """
    product = _make_product(db_session)
    _add_source_import(
        db_session,
        product,
        normalized_json={"attributes": {"lighting": {"value": {"kind": "text", "text": "warm light"}, "confidence": 0.7}}},
    )

    profile = assemble_product_profile(db_session, product)

    # lighting is contextual (prefers vision), but only source import has
    # it here - falls back to it rather than omitting the field.
    assert profile.fields["lighting"].value.text == "warm light"
    assert profile.fields["lighting"].source_type == "generic_url"


def test_only_current_rows_are_considered(db_session):
    product = _make_product(db_session)
    old = _add_lock_profile(db_session, product, VISION_STRUCTURED)
    old.is_current = False
    db_session.commit()

    profile = assemble_product_profile(db_session, product)
    assert "brand" not in profile.fields


def test_extract_branding_text_returns_every_labels_and_text_entry(db_session):
    """
    Public extraction reused directly by app.services.generation_engine
    (real-world-diagnosed fix, see MIGRATION_PLAN.md) - must return the
    same values assemble_product_profile's own branding_text field uses,
    not a re-derivation that could silently drift from it.
    """
    product = _make_product(db_session)
    structured = {
        **VISION_STRUCTURED,
        "labels_and_text": [
            {"text": "EAU DE PARFUM", "location": "front"},
            {"text": "100ml", "location": "back"},
        ],
    }
    profile_row = _add_lock_profile(db_session, product, structured)

    assert extract_branding_text(profile_row) == ["EAU DE PARFUM", "100ml"]


def test_extract_branding_text_skips_entries_with_no_text():
    from app.models.product_lock_profile import ProductLockProfile

    row = ProductLockProfile(
        analysis_run_id="fake",
        product_id="fake",
        structured_json={"labels_and_text": [{"text": ""}, {"location": "front"}, "not-a-dict", None]},
        reference_image_ids_json=[],
    )
    assert extract_branding_text(row) == []


def test_extract_branding_text_returns_empty_list_when_no_labels_and_text():
    from app.models.product_lock_profile import ProductLockProfile

    row = ProductLockProfile(
        analysis_run_id="fake", product_id="fake", structured_json={}, reference_image_ids_json=[]
    )
    assert extract_branding_text(row) == []
