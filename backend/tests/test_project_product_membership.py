"""
Tests for ProjectProduct membership auto-population - Phase 10.5 of AI
Creative Engine vNext (see MIGRATION_PLAN.md's "ADR: AI Creative Engine
vNext" §3). Linking a Product to a Slide of a Project-scoped Slideshow
(via assign-product or the additive add-product endpoint) should record
that Product as a member of the Project, observable via
GET /api/projects/{id}/products.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

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


def _create_project(client, name="My Project") -> str:
    return client.post("/api/projects", json={"name": name}).json()["id"]


def _import_slideshow(client, project_id: str | None = None) -> tuple[str, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 200), color=(10, 20, 30)).save(buffer, format="JPEG")
    data = {"project_id": project_id} if project_id else {}
    slideshow = client.post(
        "/api/slideshows/import",
        files={"files": ("t.jpg", io.BytesIO(buffer.getvalue()), "image/jpeg")},
        data=data,
    ).json()[0]
    return slideshow["id"], slideshow["slides"][0]["id"]


def _create_product(client, name: str) -> str:
    return client.post("/api/products", json={"display_name": name}).json()["id"]


def test_assign_product_records_project_membership(client):
    project_id = _create_project(client)
    slideshow_id, slide_id = _import_slideshow(client, project_id)
    product_id = _create_product(client, "Widget")

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product",
        json={"product_id": product_id},
    )
    assert response.status_code == 200

    members = client.get(f"/api/projects/{project_id}/products")
    assert members.status_code == 200
    assert [p["id"] for p in members.json()] == [product_id]


def test_add_slide_product_records_project_membership(client):
    project_id = _create_project(client)
    slideshow_id, slide_id = _import_slideshow(client, project_id)
    product_id = _create_product(client, "Widget")

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products",
        json={"product_id": product_id},
    )
    assert response.status_code == 200

    members = client.get(f"/api/projects/{project_id}/products")
    assert [p["id"] for p in members.json()] == [product_id]


def test_no_project_means_no_membership_recorded(client):
    """An unscoped Slideshow (no project_id) links a Product without error - just nothing to record."""
    slideshow_id, slide_id = _import_slideshow(client)
    product_id = _create_product(client, "Widget")

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product",
        json={"product_id": product_id},
    )
    assert response.status_code == 200


def test_linking_the_same_product_twice_does_not_duplicate_membership(client):
    project_id = _create_project(client)
    slideshow_id, slide_id = _import_slideshow(client, project_id)
    product_id = _create_product(client, "Widget")

    client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product",
        json={"product_id": product_id},
    )
    client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product",
        json={"product_id": None},
    )
    client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product",
        json={"product_id": product_id},
    )

    members = client.get(f"/api/projects/{project_id}/products").json()
    assert [p["id"] for p in members] == [product_id]


def test_list_project_products_404s_for_unknown_project(client):
    response = client.get("/api/projects/does-not-exist/products")
    assert response.status_code == 404


def test_list_project_products_empty_for_a_project_with_no_linked_products(client):
    project_id = _create_project(client)
    response = client.get(f"/api/projects/{project_id}/products")
    assert response.status_code == 200
    assert response.json() == []
