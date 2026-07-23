"""
Route-level tests for /api/listings/* and /api/bundles/* - Phase 5.11 of
the catalogue layer, see MIGRATION_PLAN.md's frozen catalogue ADR.

No real network calls: monkeypatches get_product_source_adapter at the
same import location tests/test_listing_import_service.py uses, so the
real service/route logic runs end-to-end against a fake adapter.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.product_sources.base import (
    BundleMemberHint,
    NormalizedBundleEvidence,
    NormalizedProductEvidence,
    ProductSourceExtraction,
)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class _FakeAdapter:
    def __init__(self, evidence=None, raises=None):
        self._evidence = evidence
        self._raises = raises

    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> ProductSourceExtraction:
        if self._raises:
            raise self._raises
        return ProductSourceExtraction(raw={"ok": True}, normalized=self._evidence)


def _register_fake(monkeypatch, adapter):
    monkeypatch.setattr("app.services.listing_import.get_product_source_adapter", lambda url: adapter)


def _create_product(client, name: str = "Test Product") -> str:
    return client.post("/api/products", json={"display_name": name}).json()["id"]


# --- POST /api/listings/source-import ---------------------------------------


def test_source_import_succeeds_and_stays_unresolved(client, monkeypatch):
    evidence = NormalizedProductEvidence(
        source_type="generic_url", source_url="https://shop.example/mystery", title="Widget", brand="Acme"
    )
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))

    response = client.post("/api/listings/source-import", json={"url": "https://shop.example/mystery"})

    assert response.status_code == 200
    body = response.json()
    assert body["resolved_product_id"] is None
    assert body["resolved_bundle_id"] is None


def test_source_import_failure_surfaces_without_500ing(client, monkeypatch):
    _register_fake(monkeypatch, _FakeAdapter(raises=ValueError("unreachable")))

    response = client.post("/api/listings/source-import", json={"url": "https://unreachable.example/"})

    assert response.status_code == 200
    assert response.json()["resolved_product_id"] is None


def test_source_import_denormalizes_commercial_facts(client, monkeypatch):
    from app.product_sources.base import NormalizedListingMetadata

    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/p",
        listing=NormalizedListingMetadata(price_amount=29.99, price_currency="USD"),
    )
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))

    response = client.post("/api/listings/source-import", json={"url": "https://shop.example/p"})

    assert response.json()["price_amount"] == 29.99
    assert response.json()["price_currency"] == "USD"


# --- GET /api/listings/{id} --------------------------------------------------


def test_get_listing_unknown_404s(client):
    response = client.get("/api/listings/does-not-exist")
    assert response.status_code == 404


def test_get_listing_exposes_pending_bundle_hints(client, monkeypatch):
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/bella-vita-set",
        bundle=NormalizedBundleEvidence(
            title="Bella Vita Luxury Set",
            member_hints=[BundleMemberHint(label="G.O.A.T. Man"), BundleMemberHint(label="CEO Man")],
        ),
    )
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post(
        "/api/listings/source-import", json={"url": "https://shop.example/bella-vita-set"}
    ).json()["id"]

    body = client.get(f"/api/listings/{listing_id}").json()

    assert [hint["label"] for hint in body["pending_bundle_hints"]] == ["G.O.A.T. Man", "CEO Man"]
    assert body["pending_bundle_title"] == "Bella Vita Luxury Set"


def test_get_listing_has_no_pending_hints_for_ordinary_evidence(client, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", brand="Acme")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post("/api/listings/source-import", json={"url": "https://shop.example/p"}).json()["id"]

    body = client.get(f"/api/listings/{listing_id}").json()

    assert body["pending_bundle_hints"] == []


# --- resolve-existing-product / resolve-new-product --------------------------


def test_resolve_existing_product_succeeds(client, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post("/api/listings/source-import", json={"url": "https://shop.example/p"}).json()["id"]
    product_id = _create_product(client)

    response = client.post(f"/api/listings/{listing_id}/resolve-existing-product", json={"product_id": product_id})

    assert response.status_code == 200
    assert response.json()["resolved_product_id"] == product_id


def test_resolve_existing_product_unknown_product_400s(client, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post("/api/listings/source-import", json={"url": "https://shop.example/p"}).json()["id"]

    response = client.post(
        f"/api/listings/{listing_id}/resolve-existing-product", json={"product_id": "does-not-exist"}
    )
    assert response.status_code == 400


def test_resolve_existing_product_unknown_listing_404s(client):
    response = client.post(
        "/api/listings/does-not-exist/resolve-existing-product", json={"product_id": "whatever"}
    )
    assert response.status_code == 404


def test_resolve_new_product_creates_a_product(client, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post("/api/listings/source-import", json={"url": "https://shop.example/p"}).json()["id"]

    response = client.post(
        f"/api/listings/{listing_id}/resolve-new-product", json={"display_name": "Brand New Widget"}
    )

    assert response.status_code == 200
    product_id = response.json()["resolved_product_id"]
    assert client.get(f"/api/products/{product_id}").json()["display_name"] == "Brand New Widget"


def test_resolving_an_already_resolved_listing_400s(client, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post("/api/listings/source-import", json={"url": "https://shop.example/p"}).json()["id"]
    client.post(f"/api/listings/{listing_id}/resolve-new-product", json={"display_name": "First"})

    response = client.post(
        f"/api/listings/{listing_id}/resolve-new-product", json={"display_name": "Second"}
    )
    assert response.status_code == 400


# --- resolve-existing-bundle / resolve-new-bundle + GET /api/bundles/{id} ---


def test_resolve_new_bundle_rejects_empty_members(client, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/bundle")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post("/api/listings/source-import", json={"url": "https://shop.example/bundle"}).json()["id"]

    response = client.post(
        f"/api/listings/{listing_id}/resolve-new-bundle", json={"display_name": "Empty Set", "members": []}
    )
    assert response.status_code == 400


def test_get_bundle_unknown_404s(client):
    response = client.get("/api/bundles/does-not-exist")
    assert response.status_code == 404


def test_full_bundle_flow_import_resolve_and_view(client, monkeypatch):
    """
    The plan's own stated test strategy: import a bundle-shaped listing,
    resolve each hint to a new/existing product, GET /api/bundles/{id}
    returns real member profiles - not mocked at the profile-assembly
    level, only at adapter resolution (same discipline as every other
    Product Intelligence test).
    """
    existing_product_id = _create_product(client, "G.O.A.T. Man")

    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/bella-vita-set",
        bundle=NormalizedBundleEvidence(
            title="Bella Vita Luxury Set",
            member_hints=[BundleMemberHint(label="G.O.A.T. Man"), BundleMemberHint(label="CEO Man")],
        ),
    )
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post(
        "/api/listings/source-import", json={"url": "https://shop.example/bella-vita-set"}
    ).json()["id"]

    resolve_response = client.post(
        f"/api/listings/{listing_id}/resolve-new-bundle",
        json={
            "display_name": "Bella Vita Luxury Set",
            "members": [
                {"existing_product_id": existing_product_id, "quantity": 1},
                {"new_product_display_name": "CEO Man", "quantity": 1},
            ],
        },
    )
    assert resolve_response.status_code == 200
    bundle_id = resolve_response.json()["resolved_bundle_id"]
    assert bundle_id is not None

    bundle_view = client.get(f"/api/bundles/{bundle_id}").json()

    assert bundle_view["display_name"] == "Bella Vita Luxury Set"
    assert len(bundle_view["members"]) == 2
    member_product_ids = {m["product_id"] for m in bundle_view["members"]}
    assert existing_product_id in member_product_ids
    for member in bundle_view["members"]:
        assert member["profile"]["product_id"] == member["product_id"]
        # Neither member has any real evidence yet (no vision/source-import
        # for the new one, none run for the existing one either) - the
        # point here is the shape/wiring is correct end-to-end, not that
        # the profile has content.
        assert member["profile"]["fields"] == {}


def test_resolve_existing_bundle_succeeds(client, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    listing_id = client.post("/api/listings/source-import", json={"url": "https://shop.example/p"}).json()["id"]

    existing_product_id = _create_product(client)
    first_listing = client.post(
        "/api/listings/source-import", json={"url": "https://shop.example/original-set"}
    ).json()
    bundle_id = client.post(
        f"/api/listings/{first_listing['id']}/resolve-new-bundle",
        json={"display_name": "Set", "members": [{"existing_product_id": existing_product_id}]},
    ).json()["resolved_bundle_id"]

    response = client.post(
        f"/api/listings/{listing_id}/resolve-existing-bundle", json={"bundle_id": bundle_id}
    )
    assert response.status_code == 200
    assert response.json()["resolved_bundle_id"] == bundle_id
