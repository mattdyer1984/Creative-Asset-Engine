"""
API-level tests for Products + Creative product assignment (plan §7).

Unlike the Stage/Orchestrator tests (service-layer, direct DB session),
this exercises the actual HTTP routes via FastAPI's TestClient, with
get_db overridden to use the same isolated per-test SQLite DB as
db_session - catching request/response-shape issues (status codes,
schema serialization) that a service-layer test can't.
"""

import io

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


def test_assign_and_unassign_product_on_creative(client):
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()

    image_bytes = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    import_response = client.post(
        "/api/creatives/import",
        files={"files": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
    )
    creative = import_response.json()[0]
    assert creative["product"] is None

    assign_response = client.post(
        f"/api/creatives/{creative['id']}/assign-product",
        json={"product_id": product["id"]},
    )
    assert assign_response.status_code == 200
    assigned = assign_response.json()
    assert assigned["product_id"] == product["id"]
    assert assigned["product"]["display_name"] == "Sunrise Orange Juice"

    unassign_response = client.post(
        f"/api/creatives/{creative['id']}/assign-product",
        json={"product_id": None},
    )
    assert unassign_response.json()["product_id"] is None
    assert unassign_response.json()["product"] is None


def test_assigning_unknown_product_404s(client):
    image_bytes = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    creative = client.post(
        "/api/creatives/import",
        files={"files": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
    ).json()[0]

    response = client.post(
        f"/api/creatives/{creative['id']}/assign-product",
        json={"product_id": "does-not-exist"},
    )
    assert response.status_code == 404
