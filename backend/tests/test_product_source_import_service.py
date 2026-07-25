"""
Tests for app.services.product_source_import.import_product_source
(Phase 5.3 of Product Intelligence, see MIGRATION_PLAN.md).

Orchestration is tested against a fake adapter registered via
monkeypatch (fast, deterministic, no HTTP mocking needed for adapter
resolution itself - GenericUrlAdapter's own parsing is already covered
by tests/test_generic_product_source_adapter.py). The image-download
step is the service's own logic, not delegated to the adapter, so that
part is tested with a real httpx.MockTransport.
"""

import httpx

from app.models.product import Product
from app.models.product_reference_image import ProductReferenceImage
from app.models.product_source_import import FETCH_STATUS_FAILED, FETCH_STATUS_SUCCEEDED
from app.product_sources.base import (
    NormalizedAttribute,
    NormalizedProductEvidence,
    NormalizedProductImage,
    ProductSourceExtraction,
    TextValue,
)
from app.services.product_source_import import import_product_source


def _make_product(db_session) -> Product:
    product = Product(display_name="Test Product")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


class _FakeSucceedingAdapter:
    def __init__(self, evidence: NormalizedProductEvidence):
        self._evidence = evidence

    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> ProductSourceExtraction:
        return ProductSourceExtraction(raw={"fake": "raw-data"}, normalized=self._evidence)


class _FakeFailingAdapter:
    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> ProductSourceExtraction:
        raise ValueError("simulated extraction failure")


def _register_fake(monkeypatch, adapter_instance):
    monkeypatch.setattr(
        "app.services.product_source_import.get_product_source_adapter", lambda url: adapter_instance
    )


def test_successful_import_persists_raw_and_normalized(db_session, monkeypatch):
    product = _make_product(db_session)
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/p",
        title="Widget",
        brand="Acme",
        attributes={"brand": NormalizedAttribute(value=TextValue(text="Acme"), confidence=0.9)},
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    result = import_product_source(db_session, product.id, "https://shop.example/p")

    assert result.fetch_status == FETCH_STATUS_SUCCEEDED
    assert result.source_type == "generic_url"
    assert result.raw_response_json == {"fake": "raw-data"}
    assert result.normalized_json["title"] == "Widget"
    assert result.is_current is True
    assert result.error is None


def test_a_200_response_with_nothing_extractable_is_partial_not_succeeded(db_session, monkeypatch):
    """
    Found via live testing against a real TikTok Shop URL (Phase 5.7):
    an HTTP 200 response that's genuinely just a bot-detection wall has
    no error to raise, but extracted no title/brand/attributes/images
    either - marking that FETCH_STATUS_SUCCEEDED would misleadingly
    imply real product evidence was found.
    """
    from app.models.product_source_import import FETCH_STATUS_PARTIAL

    product = _make_product(db_session)
    evidence = NormalizedProductEvidence(
        source_type="generic_url", source_url="https://shop.example/blocked", title=None
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    result = import_product_source(db_session, product.id, "https://shop.example/blocked")

    assert result.fetch_status == FETCH_STATUS_PARTIAL


def test_failed_extraction_records_failed_import_not_an_exception(db_session, monkeypatch):
    product = _make_product(db_session)
    _register_fake(monkeypatch, _FakeFailingAdapter())

    result = import_product_source(db_session, product.id, "https://shop.example/broken")

    assert result.fetch_status == FETCH_STATUS_FAILED
    assert "simulated extraction failure" in result.error
    assert result.raw_response_json is None
    assert result.normalized_json is None


def test_second_import_flips_is_current_on_the_first(db_session, monkeypatch):
    product = _make_product(db_session)
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", title="V1")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    first = import_product_source(db_session, product.id, "https://shop.example/p")

    evidence_v2 = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", title="V2")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence_v2))
    second = import_product_source(db_session, product.id, "https://shop.example/p")

    db_session.refresh(first)
    assert first.is_current is False
    assert second.is_current is True


def test_downloads_discovered_images_into_reference_images(db_session, monkeypatch):
    product = _make_product(db_session)
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/p",
        images=[NormalizedProductImage(url="https://cdn.example.com/hero.jpg", role="primary")],
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\xff\xd8\xff\xe0fake-jpeg-bytes")

    result = import_product_source(
        db_session, product.id, "https://shop.example/p", image_download_transport=httpx.MockTransport(handler)
    )

    images = list(
        db_session.query(ProductReferenceImage).filter(
            ProductReferenceImage.source_product_source_import_id == result.id
        )
    )
    assert len(images) == 1
    assert images[0].analysis_run_id is None
    assert images[0].isolation_method == "product_url"
    assert images[0].file_path != ""


def test_a_failed_image_download_does_not_fail_the_whole_import(db_session, monkeypatch):
    product = _make_product(db_session)
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/p",
        title="Widget",
        images=[NormalizedProductImage(url="https://cdn.example.com/missing.jpg")],
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    result = import_product_source(
        db_session, product.id, "https://shop.example/p", image_download_transport=httpx.MockTransport(handler)
    )

    assert result.fetch_status == FETCH_STATUS_SUCCEEDED
    assert result.normalized_json["title"] == "Widget"
    images = list(
        db_session.query(ProductReferenceImage).filter(
            ProductReferenceImage.source_product_source_import_id == result.id
        )
    )
    assert images == []


def test_unknown_product_id_still_records_a_failed_import_via_registry_error(db_session, monkeypatch):
    """
    get_product_source_adapter itself never validates product_id - a
    genuinely unmatched URL (real registry, no fake) is what would raise
    here in production; simulated the same way extraction failures are.
    """
    _register_fake(monkeypatch, _FakeFailingAdapter())
    result = import_product_source(db_session, "does-not-exist", "https://shop.example/x")
    assert result.fetch_status == FETCH_STATUS_FAILED


def test_a_non_image_payload_is_rejected_not_saved(db_session, monkeypatch):
    """
    SSRF hardening (Phase 0, WP-0C): image URLs come from the fetched
    page's own markup, so a hostile page can point them anywhere. Even
    when the fetch itself succeeds, content that is not actually an image
    must not be written to disk - a Content-Type header proves nothing.
    """
    product = _make_product(db_session)
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/p",
        images=[NormalizedProductImage(url="https://cdn.example.com/not-really.jpg", role="primary")],
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    def handler(request: httpx.Request) -> httpx.Response:
        # 200 OK, claims to be an image, actually HTML.
        return httpx.Response(
            200, content=b"<!DOCTYPE html><html>gotcha", headers={"content-type": "image/jpeg"}
        )

    result = import_product_source(
        db_session, product.id, "https://shop.example/p", image_download_transport=httpx.MockTransport(handler)
    )

    images = list(
        db_session.query(ProductReferenceImage).filter(
            ProductReferenceImage.source_product_source_import_id == result.id
        )
    )
    assert images == [], "non-image content must not be persisted as a reference image"
