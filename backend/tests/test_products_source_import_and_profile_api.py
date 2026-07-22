"""
Route-level tests for POST /api/products/{id}/source-import and
GET /api/products/{id}/profile - Phase 5.6 of Product Intelligence, see
MIGRATION_PLAN.md.

No real network calls: monkeypatches get_product_source_adapter at the
same import location tests/test_product_source_import_service.py uses,
so the real import_product_source/route logic runs end-to-end (request
parsing, status codes, response schema) against a fake adapter.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.product_sources.base import NormalizedProductEvidence, ProductSourceExtraction


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
    monkeypatch.setattr("app.services.product_source_import.get_product_source_adapter", lambda url: adapter)


def _create_product(client) -> str:
    return client.post("/api/products", json={"display_name": "Test Product"}).json()["id"]


def test_source_import_succeeds(client, monkeypatch):
    product_id = _create_product(client)
    # brand set, not just title - a bare title alone is FETCH_STATUS_PARTIAL
    # (see app.services.product_source_import._fetch_status_for), too weak
    # a signal on its own to count as "real product evidence was found".
    evidence = NormalizedProductEvidence(
        source_type="generic_url", source_url="https://shop.example/p", title="Widget", brand="Acme"
    )
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))

    response = client.post(f"/api/products/{product_id}/source-import", json={"url": "https://shop.example/p"})

    assert response.status_code == 200
    body = response.json()
    assert body["fetch_status"] == "succeeded"
    assert body["source_type"] == "generic_url"
    assert body["error"] is None


def test_source_import_with_only_a_title_is_partial(client, monkeypatch):
    """
    Companion to test_source_import_succeeds - a bare title with no
    brand/attributes/images (e.g. a bot-detection interstitial's page
    title, confirmed live against a real TikTok Shop URL in Phase 5.7)
    is marked partial, not succeeded.
    """
    product_id = _create_product(client)
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", title="Security Check")
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))

    response = client.post(f"/api/products/{product_id}/source-import", json={"url": "https://shop.example/p"})

    assert response.status_code == 200
    assert response.json()["fetch_status"] == "partial"


def test_source_import_surfaces_failure_without_500ing(client, monkeypatch):
    product_id = _create_product(client)
    _register_fake(monkeypatch, _FakeAdapter(raises=ValueError("unreachable")))

    response = client.post(f"/api/products/{product_id}/source-import", json={"url": "https://unreachable.example/"})

    assert response.status_code == 200
    body = response.json()
    assert body["fetch_status"] == "failed"
    assert "unreachable" in body["error"]


def test_source_import_unknown_product_404s(client, monkeypatch):
    _register_fake(monkeypatch, _FakeAdapter(evidence=NormalizedProductEvidence(source_type="generic_url", source_url="x")))
    response = client.post("/api/products/does-not-exist/source-import", json={"url": "https://shop.example/p"})
    assert response.status_code == 404


def test_profile_is_empty_for_a_product_with_no_evidence(client):
    product_id = _create_product(client)
    response = client.get(f"/api/products/{product_id}/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == product_id
    assert body["fields"] == {}


def test_profile_reflects_a_successful_source_import(client, monkeypatch):
    product_id = _create_product(client)
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/p",
        attributes={
            "brand": {"value": {"kind": "text", "text": "Acme"}, "confidence": 0.9},
        },
    )
    _register_fake(monkeypatch, _FakeAdapter(evidence=evidence))
    client.post(f"/api/products/{product_id}/source-import", json={"url": "https://shop.example/p"})

    body = client.get(f"/api/products/{product_id}/profile").json()

    assert body["fields"]["brand"]["value"]["text"] == "Acme"
    assert body["fields"]["brand"]["classification"] == "immutable"
    assert body["fields"]["brand"]["source_type"] == "generic_url"


def test_profile_unknown_product_404s(client):
    response = client.get("/api/products/does-not-exist/profile")
    assert response.status_code == 404
