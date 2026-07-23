"""
Regression test for a bug found while auditing before Phase 2.7:
GET /api/products/{id}/reference-images 500'd (ResponseValidationError)
the moment any ProductReferenceImage created by the new pipeline existed
for a product, because ProductReferenceImageRead.source_creative_id was
still typed as non-nullable str even after Phase 2.3 made the underlying
column nullable (the new pipeline populates source_slide_id instead).

Reproduced directly against a live TestClient before fixing - this test
locks the fix in place.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db import get_db
from app.main import app
from app.models.slideshow import Slideshow
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from tests.fakes import FakeAIProviderRegistry


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_reference_images_endpoint_handles_new_pipeline_rows(client, db_session, monkeypatch):
    product = client.post("/api/products", json={"display_name": "Bug Check Product"}).json()

    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), color=(50, 60, 70)).save(buffer, format="JPEG")
    slideshow = client.post(
        "/api/slideshows/import",
        files={"files": ("t.jpg", io.BytesIO(buffer.getvalue()), "image/jpeg")},
    ).json()[0]
    slide_id = slideshow["slides"][0]["id"]
    client.post(
        f"/api/slideshows/{slideshow['id']}/slides/{slide_id}/assign-product",
        json={"product_id": product["id"]},
    )

    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    ss = db_session.get(Slideshow, slideshow["id"])
    result = SlideProductIsolationStage().run(db_session, ss)
    assert result.succeeded is True

    response = client.get(f"/api/products/{product['id']}/reference-images")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source_creative_id"] is None
