"""
API-level tests for the assembled Creative Blueprint view and per-stage
rerun endpoint (plan §1 principle 7, §11 M7).
"""

import io

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from tests.fakes import FakeAIProviderRegistry, FakeVisionAnalysisProvider
from tests.test_creative_fingerprint_stage import FINGERPRINT_RESULT


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _import_creative_with_product(client) -> tuple[str, str]:
    from io import BytesIO

    from PIL import Image

    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()

    # A real, decodable JPEG - Product Isolation actually opens and crops
    # the image via Pillow, unlike some other stages that never touch
    # image content (learned this the hard way building M4's fixtures).
    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=(210, 160, 120)).save(buffer, format="JPEG")
    image_bytes = buffer.getvalue()

    creative = client.post(
        "/api/creatives/import",
        files={"files": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
    ).json()[0]
    client.post(f"/api/creatives/{creative['id']}/assign-product", json={"product_id": product["id"]})
    return creative["id"], product["id"]


def test_blueprint_is_all_null_for_a_fresh_creative(client):
    creative_id, _ = _import_creative_with_product(client)

    response = client.get(f"/api/creatives/{creative_id}/blueprint")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "imported"
    assert body["ocr_result"] is None
    assert body["product_lock_profile"] is None
    assert body["creative_fingerprint"] is None
    assert body["marketing_analysis"] is None
    assert body["recreation_prompt"] is None
    assert body["product_reference_images"] == []
    assert body["failed_stage"] is None


def test_blueprint_unknown_creative_404s(client):
    response = client.get("/api/creatives/does-not-exist/blueprint")
    assert response.status_code == 404


def test_rerun_unknown_stage_400s(client):
    creative_id, _ = _import_creative_with_product(client)
    response = client.post(f"/api/creatives/{creative_id}/stages/not_a_real_stage/rerun")
    assert response.status_code == 400


def test_rerun_unknown_creative_404s(client):
    response = client.post("/api/creatives/does-not-exist/stages/ocr/rerun")
    assert response.status_code == 404


def test_rerun_ocr_populates_blueprint_and_returns_it(client, monkeypatch):
    creative_id, _ = _import_creative_with_product(client)

    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    response = client.post(f"/api/creatives/{creative_id}/stages/ocr/rerun")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ready"
    assert body["ocr_result"] is not None
    assert body["ocr_result"]["raw_text"] == "Fresh Squeezed. Zero Sugar Added."
    # Other artifacts correctly still absent - OCR alone doesn't produce them.
    assert body["creative_fingerprint"] is None


def test_rerun_reflects_failure_in_the_assembled_blueprint(client, monkeypatch):
    """Rerunning Recreation Prompt with no prerequisites met should fail and show up
    clearly in the assembled response."""
    creative_id, _ = _import_creative_with_product(client)

    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )
    response = client.post(f"/api/creatives/{creative_id}/stages/recreation_prompt/rerun")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "failed"
    assert body["failed_stage"] == "recreation_prompt"
    assert "No Product Lock Profile" in body["failed_stage_error"]
    assert body["recreation_prompt"] is None


def test_analyze_surfaces_prerequisite_failure_with_no_product_assigned(client, monkeypatch):
    """
    The exact scenario that motivated fixing run_full_pipeline's return
    value: importing a creative and clicking Analyze WITHOUT assigning a
    product first is entirely possible in the UI (nothing currently gates
    the Analyze button on product assignment). OCR succeeds, then Product
    Isolation fails its prerequisite check before creating any
    AnalysisRun - /analyze's response must still name exactly what failed.
    """
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=(200, 150, 90)).save(buffer, format="JPEG")
    creative = client.post(
        "/api/creatives/import",
        files={"files": ("test.jpg", BytesIO(buffer.getvalue()), "image/jpeg")},
    ).json()[0]
    # Deliberately no assign-product call.

    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    response = client.post(f"/api/creatives/{creative['id']}/analyze")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "failed"
    assert body["failed_stage"] == "product_isolation"
    assert "No product assigned" in body["failed_stage_error"]
    # OCR's output survives even though the overall pipeline failed later.
    assert body["ocr_result"] is not None


def test_failure_info_survives_a_separate_later_get_not_just_the_triggering_response(client, monkeypatch):
    """
    Found by actually looking at the rendered UI, not just checking the
    API response immediately after triggering: a fresh GET /blueprint -
    e.g. the user closes and reopens the Blueprint, or just loads the
    page later - must show the same failure info as the response that
    came back from the original POST /analyze. It's not enough for the
    failure to be visible only in the single response of the request
    that caused it.
    """
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=(200, 150, 90)).save(buffer, format="JPEG")
    creative = client.post(
        "/api/creatives/import",
        files={"files": ("test.jpg", BytesIO(buffer.getvalue()), "image/jpeg")},
    ).json()[0]
    # No product assigned.

    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())
    client.post(f"/api/creatives/{creative['id']}/analyze")

    # A separate, later GET - not the response of the POST above.
    later_response = client.get(f"/api/creatives/{creative['id']}/blueprint")
    body = later_response.json()

    assert body["status"] == "failed"
    assert body["failed_stage"] == "product_isolation"
    assert "No product assigned" in body["failed_stage_error"]


def test_blueprint_reflects_full_pipeline_results(client, monkeypatch):
    creative_id, _ = _import_creative_with_product(client)

    monkeypatch.setattr("app.stages.ocr_stage.default_registry", FakeAIProviderRegistry())
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    monkeypatch.setattr(
        "app.stages.marketing_analysis_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    response = client.post(f"/api/creatives/{creative_id}/analyze")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

    blueprint = client.get(f"/api/creatives/{creative_id}/blueprint").json()
    assert blueprint["status"] == "ready"
    assert blueprint["ocr_result"] is not None
    assert len(blueprint["product_reference_images"]) == 1
    assert blueprint["product_lock_profile"] is not None
    assert blueprint["creative_fingerprint"] is not None
    assert blueprint["marketing_analysis"] is not None
    assert blueprint["recreation_prompt"] is not None
    assert blueprint["recreation_prompt"]["structured"]["product_lock_reference"][
        "product_lock_profile_id"
    ] == blueprint["product_lock_profile"]["id"]
