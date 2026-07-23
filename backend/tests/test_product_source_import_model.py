"""
Unit tests for the ProductSourceImport model and the ProductReferenceImage
extension that goes with it - Phase 5.1 of Product Intelligence (see
MIGRATION_PLAN.md). Additive schema only; no service/API code exists yet
to exercise, so these are model-level round-trip tests, mirroring
tests/test_slideshow_model.py's style for Phase 4.1's equivalent change.
"""

from app.models.product import Product
from app.models.product_reference_image import ProductReferenceImage
from app.models.product_source_import import (
    FETCH_STATUS_FAILED,
    FETCH_STATUS_SUCCEEDED,
    ProductSourceImport,
)


def _make_product(db_session) -> Product:
    product = Product(display_name="Test Product")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def test_product_source_import_round_trips_a_succeeded_fetch(db_session):
    product = _make_product(db_session)

    import_row = ProductSourceImport(
        product_id=product.id,
        source_type="generic_url",
        source_url="https://example.com/products/widget",
        fetch_status=FETCH_STATUS_SUCCEEDED,
        raw_response_json={"title": "Widget", "og:image": "https://example.com/w.jpg"},
        normalized_json={"title": {"kind": "text", "text": "Widget"}},
    )
    db_session.add(import_row)
    db_session.commit()
    db_session.refresh(import_row)

    assert import_row.id is not None
    assert import_row.is_current is True
    assert import_row.error is None
    assert import_row.raw_response_json["title"] == "Widget"
    assert import_row.normalized_json["title"]["text"] == "Widget"
    assert import_row.created_at is not None


def test_product_source_import_round_trips_a_failed_fetch_with_no_response(db_session):
    """
    A failed fetch (e.g. the URL was unreachable) may have no raw response
    at all - both JSON columns must tolerate None, not just an empty dict.
    """
    product = _make_product(db_session)

    import_row = ProductSourceImport(
        product_id=product.id,
        source_type="generic_url",
        source_url="https://unreachable.example.invalid/",
        fetch_status=FETCH_STATUS_FAILED,
        error="Connection timed out",
        raw_response_json=None,
        normalized_json=None,
    )
    db_session.add(import_row)
    db_session.commit()
    db_session.refresh(import_row)

    assert import_row.fetch_status == FETCH_STATUS_FAILED
    assert import_row.error == "Connection timed out"
    assert import_row.raw_response_json is None
    assert import_row.normalized_json is None


def test_product_reference_image_accepts_url_sourced_row_with_no_analysis_run(db_session):
    """
    The real point of Phase 5.1's ProductReferenceImage change: a row
    sourced from a Product Source import has no AnalysisRun to point at
    (a URL fetch isn't an AI call) - analysis_run_id must accept None,
    unlike every other artifact using AnalysisArtifactMixin.
    """
    product = _make_product(db_session)
    import_row = ProductSourceImport(
        product_id=product.id,
        source_type="generic_url",
        source_url="https://example.com/products/widget",
        fetch_status=FETCH_STATUS_SUCCEEDED,
    )
    db_session.add(import_row)
    db_session.flush()

    image = ProductReferenceImage(
        product_id=product.id,
        analysis_run_id=None,
        source_product_source_import_id=import_row.id,
        file_path="/tmp/official.jpg",
        isolation_method="product_url",
    )
    db_session.add(image)
    db_session.commit()
    db_session.refresh(image)

    assert image.analysis_run_id is None
    assert image.source_product_source_import_id == import_row.id
    assert image.source_slide_id is None
