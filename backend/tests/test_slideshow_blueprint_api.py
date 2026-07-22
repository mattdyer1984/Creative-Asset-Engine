"""
API-level tests for the new /api/slideshows/* surface (Phase 2.5 of the
Slideshow/Slide migration) - mirrors tests/test_creative_blueprint_api.py's
coverage of the old /api/creatives/* surface.
"""

import io

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from tests.fakes import FakeAIProviderRegistry, FakeVisionAnalysisProvider
from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _import_slideshow_with_product(client) -> tuple[str, str, str]:
    """Returns (slideshow_id, slide_id, product_id)."""
    from io import BytesIO

    from PIL import Image

    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()

    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=(210, 160, 120)).save(buffer, format="JPEG")
    image_bytes = buffer.getvalue()

    slideshow = client.post(
        "/api/slideshows/import",
        files={"files": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
    ).json()[0]
    slide_id = slideshow["slides"][0]["id"]
    client.post(
        f"/api/slideshows/{slideshow['id']}/slides/{slide_id}/assign-product",
        json={"product_id": product["id"]},
    )
    return slideshow["id"], slide_id, product["id"]


def _import_slideshow(client) -> str:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=(200, 150, 90)).save(buffer, format="JPEG")
    slideshow = client.post(
        "/api/slideshows/import",
        files={"files": ("test.jpg", BytesIO(buffer.getvalue()), "image/jpeg")},
    ).json()[0]
    return slideshow["id"]


def test_blueprint_is_all_null_for_a_fresh_slideshow(client):
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    response = client.get(f"/api/slideshows/{slideshow_id}/blueprint")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "imported"
    assert len(body["slides"]) == 1
    slide = body["slides"][0]
    assert slide["ocr_result"] is None
    assert slide["product_lock_profile"] is None
    assert slide["creative_fingerprint"] is None
    assert body["marketing_analysis"] is None
    assert body["recreation_prompt"] is None
    assert body["failed_stage"] is None


def test_blueprint_unknown_slideshow_404s(client):
    response = client.get("/api/slideshows/does-not-exist/blueprint")
    assert response.status_code == 404


def test_rerun_unknown_stage_400s(client):
    slideshow_id, _, _ = _import_slideshow_with_product(client)
    response = client.post(f"/api/slideshows/{slideshow_id}/stages/not_a_real_stage/rerun")
    assert response.status_code == 400


def test_rerun_unknown_slideshow_404s(client):
    response = client.post("/api/slideshows/does-not-exist/stages/ocr/rerun")
    assert response.status_code == 404


def test_rerun_ocr_populates_blueprint_and_returns_it(client, monkeypatch):
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    response = client.post(f"/api/slideshows/{slideshow_id}/stages/ocr/rerun")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ready"
    slide = body["slides"][0]
    assert slide["ocr_result"] is not None
    assert slide["ocr_result"]["raw_text"] == "Fresh Squeezed. Zero Sugar Added."
    assert slide["creative_fingerprint"] is None


def test_rerun_reflects_failure_in_the_assembled_blueprint(client, monkeypatch):
    """Rerunning Recreation Prompt with no prerequisites met should fail and show up clearly."""
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )
    response = client.post(f"/api/slideshows/{slideshow_id}/stages/recreation_prompt/rerun")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "failed"
    assert body["failed_stage"] == "recreation_prompt"
    assert "No Product Lock Profile" in body["failed_stage_error"]
    assert body["recreation_prompt"] is None


def test_analyze_surfaces_prerequisite_failure_with_no_product_assigned(client, monkeypatch):
    """
    Importing a slideshow and clicking Analyze WITHOUT assigning a
    product first: OCR succeeds, then Product Isolation fails its
    prerequisite check before creating any AnalysisRun - /analyze's
    response must still name exactly what failed.
    """
    slideshow_id = _import_slideshow(client)
    # Deliberately no assign-product call.

    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    response = client.post(f"/api/slideshows/{slideshow_id}/analyze")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "failed"
    assert body["failed_stage"] == "product_isolation"
    assert "No product assigned" in body["failed_stage_error"]
    # OCR's output survives even though the overall pipeline failed later.
    assert body["slides"][0]["ocr_result"] is not None


def test_failure_info_survives_a_separate_later_get_not_just_the_triggering_response(client, monkeypatch):
    """
    A fresh GET /blueprint - not the response of the original POST -
    must show the same failure info.
    """
    slideshow_id = _import_slideshow(client)

    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())
    client.post(f"/api/slideshows/{slideshow_id}/analyze")

    later_response = client.get(f"/api/slideshows/{slideshow_id}/blueprint")
    body = later_response.json()

    assert body["status"] == "failed"
    assert body["failed_stage"] == "product_isolation"
    assert "No product assigned" in body["failed_stage_error"]


def test_blueprint_reflects_full_pipeline_results(client, monkeypatch):
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    response = client.post(f"/api/slideshows/{slideshow_id}/analyze")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

    blueprint = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    assert blueprint["status"] == "ready"
    slide = blueprint["slides"][0]
    assert slide["ocr_result"] is not None
    assert len(slide["product_reference_images"]) == 1
    assert slide["product_lock_profile"] is not None
    assert slide["creative_fingerprint"] is not None
    assert blueprint["marketing_analysis"] is not None
    assert blueprint["recreation_prompt"] is not None
    assert blueprint["recreation_prompt"]["structured"]["product_lock_reference"][
        "product_lock_profile_id"
    ] == slide["product_lock_profile"]["id"]


def test_old_creatives_surface_is_completely_unaffected(client, monkeypatch):
    """
    Direct proof, not just an assertion by inspection: importing and
    analyzing via the OLD /api/creatives/* surface still works exactly
    as before, completely independent of the new /api/slideshows/*
    surface added in this same phase.
    """
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=(180, 120, 60)).save(buffer, format="JPEG")
    creative = client.post(
        "/api/creatives/import",
        files={"files": ("old.jpg", BytesIO(buffer.getvalue()), "image/jpeg")},
    ).json()[0]

    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())
    response = client.post(f"/api/creatives/{creative['id']}/stages/ocr/rerun")

    assert response.status_code == 200
    assert response.json()["ocr_result"]["raw_text"] == "Fresh Squeezed. Zero Sugar Added."
