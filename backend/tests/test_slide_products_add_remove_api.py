"""
Route-level tests for the additive product-appearance endpoints - Phase
6.1 of multi per-slide product detection, see MIGRATION_PLAN.md:
POST/DELETE /api/slideshows/{id}/slides/{slide_id}/products.
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


def _import_slideshow(client) -> tuple[str, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 200), color=(10, 20, 30)).save(buffer, format="JPEG")
    slideshow = client.post(
        "/api/slideshows/import",
        files={"files": ("t.jpg", io.BytesIO(buffer.getvalue()), "image/jpeg")},
    ).json()[0]
    return slideshow["id"], slideshow["slides"][0]["id"]


def _create_product(client, name: str) -> str:
    return client.post("/api/products", json={"display_name": name}).json()["id"]


def test_add_product_creates_a_current_appearance(client):
    slideshow_id, slide_id = _import_slideshow(client)
    product_id = _create_product(client, "Widget")

    response = client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": product_id})

    assert response.status_code == 200
    slide = response.json()["slides"][0]
    assert slide["current_product_appearance"]["product_id"] == product_id


def test_add_two_different_products_both_stay_current(client):
    """The actual point of Phase 6.1: assign-product's single-slot replace semantics don't apply here."""
    slideshow_id, slide_id = _import_slideshow(client)
    product_a = _create_product(client, "A")
    product_b = _create_product(client, "B")

    client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": product_a})
    client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": product_b})

    blueprint = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    product_ids = {a["product_id"] for a in blueprint["slides"][0]["product_appearances"]}
    assert product_ids == {product_a, product_b}


def test_adding_the_same_product_twice_is_idempotent_not_a_duplicate(client):
    slideshow_id, slide_id = _import_slideshow(client)
    product_id = _create_product(client, "Widget")

    client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": product_id})
    client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": product_id})

    blueprint = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    appearances = blueprint["slides"][0]["product_appearances"]
    assert len(appearances) == 1


def test_add_product_unknown_product_404s(client):
    slideshow_id, slide_id = _import_slideshow(client)
    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": "does-not-exist"}
    )
    assert response.status_code == 404


def test_add_product_unknown_slide_404s(client):
    slideshow_id, _ = _import_slideshow(client)
    product_id = _create_product(client, "Widget")
    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/does-not-exist/products", json={"product_id": product_id}
    )
    assert response.status_code == 404


def test_remove_one_appearance_leaves_the_others(client):
    slideshow_id, slide_id = _import_slideshow(client)
    product_a = _create_product(client, "A")
    product_b = _create_product(client, "B")

    client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": product_a})
    client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products", json={"product_id": product_b})

    # SlideshowRead/SlideRead only expose the singular current_product_
    # appearance - the full list (with each appearance's own id) is only
    # on the assembled blueprint's product_appearances.
    blueprint_before = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    appearance_b_id = next(
        a["id"]
        for a in blueprint_before["slides"][0]["product_appearances"]
        if a["product_id"] == product_b
    )

    response = client.delete(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products/{appearance_b_id}")

    assert response.status_code == 200
    blueprint = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    remaining = {a["product_id"] for a in blueprint["slides"][0]["product_appearances"]}
    assert remaining == {product_a}


def test_remove_unknown_appearance_404s(client):
    slideshow_id, slide_id = _import_slideshow(client)
    response = client.delete(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products/does-not-exist")
    assert response.status_code == 404


def test_assign_product_flow_is_completely_unaffected(client):
    """
    Regression guard: the existing single-slot assign-product endpoint
    (unchanged by Phase 6.1) still replaces, not adds - proving the new
    additive endpoints are genuinely parallel, not a modification of it.
    """
    slideshow_id, slide_id = _import_slideshow(client)
    product_a = _create_product(client, "A")
    product_b = _create_product(client, "B")

    client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product", json={"product_id": product_a}
    )
    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product", json={"product_id": product_b}
    )

    assert response.json()["slides"][0]["current_product_appearance"]["product_id"] == product_b
    blueprint = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    assert len(blueprint["slides"][0]["product_appearances"]) == 1
