"""
API-level tests for Products (plan §7) - pure Product CRUD, unrelated to
the Slideshow/Slide migration (Product/ProductLockProfile/
ProductReferenceImage don't move in that migration).

Unlike the Stage/Orchestrator tests (service-layer, direct DB session),
this exercises the actual HTTP routes via FastAPI's TestClient, with
get_db overridden to use the same isolated per-test SQLite DB as
db_session - catching request/response-shape issues (status codes,
schema serialization) that a service-layer test can't.

Product-assignment tests (assign/unassign, assigning an unknown product)
used to live here against the old /api/creatives/*'s Creative-level
assignment - removed in Phase 2.7 of the Slideshow/Slide migration along
with that endpoint; their new-pipeline equivalents, against
/api/slideshows/*'s Slide-level assignment, live in
test_slideshow_blueprint_api.py instead.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_and_list_products(client):
    response = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"})
    assert response.status_code == 201
    product = response.json()
    assert product["display_name"] == "Sunrise Orange Juice"
    assert product["project_id"] is None

    listed = client.get("/api/products").json()
    assert len(listed) == 1
    assert listed[0]["id"] == product["id"]


def test_get_unknown_product_404s(client):
    response = client.get("/api/products/does-not-exist")
    assert response.status_code == 404


def test_creating_product_with_unknown_project_404s(client):
    response = client.post(
        "/api/products", json={"display_name": "Test", "project_id": "does-not-exist"}
    )
    assert response.status_code == 404
