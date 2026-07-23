"""
API-level tests for the Phase 8.3 generate-image / generated-images/file
endpoints (see MIGRATION_PLAN.md's Phase 8 architecture direction). No
real OpenAI call - FakeAIProviderRegistry throughout.
"""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.product_reference_image import ProductReferenceImage
from tests.fakes import FakeAIProviderRegistry, FakeTextGenerationProvider, FakeVisionAnalysisProvider
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


def _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session):
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
        "app.slideshow_stages.narrative_structure_stage.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(
                result={"slides": [{"slide_index": 0, "beat": "hook"}], "arc_summary": "A short arc."}
            )
        ),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_specification_stage.default_registry", FakeAIProviderRegistry()
    )
    client.post(f"/api/slideshows/{slideshow_id}/analyze")

    # Phase 9.3 of Product Lock v2 (see MIGRATION_PLAN.md) - Image
    # Generation now requires a populated Canonical Reference Library.
    # Marked directly rather than re-running Reference Scoring's own AI
    # call here - that Stage has its own dedicated test file.
    current_reference_images = db_session.scalars(
        select(ProductReferenceImage).where(ProductReferenceImage.is_current.is_(True))
    ).all()
    for reference_image in current_reference_images:
        reference_image.library_status = "included"
        reference_image.role = "front"
        reference_image.quality_score = 0.8
    db_session.commit()


def test_generate_image_fails_cleanly_without_a_creative_specification(client):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)

    response = client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-image")

    assert response.status_code == 422
    assert "No Creative Specification" in response.json()["detail"]


def test_generate_image_404s_for_unknown_slideshow(client):
    response = client.post("/api/slideshows/does-not-exist/slides/also-fake/generate-image")
    assert response.status_code == 404


def test_generate_image_400s_for_a_non_primary_slide_id(client):
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    response = client.post(f"/api/slideshows/{slideshow_id}/slides/not-the-primary-slide/generate-image")

    assert response.status_code == 400
    assert "primary slide" in response.json()["detail"]


def test_generate_image_succeeds_and_file_is_servable(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)

    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )

    response = client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-image")
    assert response.status_code == 201
    body = response.json()
    assert body["slide_id"] == slide_id
    assert body["is_current"] is True
    assert body["provider"] == "openai"
    assert body["prompt_used"]

    file_response = client.get(f"/api/slideshows/{slideshow_id}/generated-images/{body['id']}/file")
    assert file_response.status_code == 200
    assert file_response.content  # real bytes were written and served back


def test_generated_image_file_404s_for_unknown_id(client):
    slideshow_id, _, _ = _import_slideshow_with_product(client)
    response = client.get(f"/api/slideshows/{slideshow_id}/generated-images/does-not-exist/file")
    assert response.status_code == 404


def test_get_current_generated_image_404s_when_none_exists_yet(client):
    """Phase 8.5 - lets the frontend check without spending a real regeneration call."""
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    response = client.get(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generated-image")
    assert response.status_code == 404


def test_get_current_generated_image_returns_the_real_current_one(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )
    created = client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-image").json()

    response = client.get(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generated-image")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def _generate_image(client, monkeypatch, slideshow_id, slide_id, db_session) -> str:
    """Runs the full pipeline through a real (fake-backed) GeneratedImage, returns its id."""
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    monkeypatch.setattr(
        "app.slideshow_stages.image_generation_stage.default_registry", FakeAIProviderRegistry()
    )
    return client.post(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-image").json()["id"]


def test_validate_image_404s_for_unknown_generated_image(client):
    slideshow_id, _, _ = _import_slideshow_with_product(client)
    response = client.post(f"/api/slideshows/{slideshow_id}/generated-images/does-not-exist/validate")
    assert response.status_code == 404


def test_validate_image_succeeds_and_surfaces_field_checks(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    generated_image_id = _generate_image(client, monkeypatch, slideshow_id, slide_id, db_session)

    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": {
                "field_checks": [{"field_name": "silhouette", "preserved": True, "reason": "Matches."}]
            },
            "image_validation": {
                "field_checks": [
                    {"field_name": "brand", "preserved": True, "reason": "Matches."},
                    {"field_name": "color", "preserved": False, "reason": "Wrong shade of orange."},
                ],
                "overall_explanation": "One characteristic did not match.",
            },
        }
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    response = client.post(f"/api/slideshows/{slideshow_id}/generated-images/{generated_image_id}/validate")

    assert response.status_code == 201
    body = response.json()
    assert body["generated_image_id"] == generated_image_id
    assert body["passed"] is False
    assert body["overall_explanation"] == "One characteristic did not match."
    assert body["field_checks"] == [
        {"field_name": "brand", "preserved": True, "reason": "Matches."},
        {"field_name": "color", "preserved": False, "reason": "Wrong shade of orange."},
    ]


def test_get_current_validation_result_404s_when_none_exists_yet(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    generated_image_id = _generate_image(client, monkeypatch, slideshow_id, slide_id, db_session)

    response = client.get(f"/api/slideshows/{slideshow_id}/generated-images/{generated_image_id}/validation")

    assert response.status_code == 404


def test_get_current_validation_result_returns_the_real_current_one(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    generated_image_id = _generate_image(client, monkeypatch, slideshow_id, slide_id, db_session)

    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(
            vision_provider=FakeVisionAnalysisProvider(
                results_by_schema_name={
                    "identity_validation": {
                        "field_checks": [{"field_name": "silhouette", "preserved": True, "reason": "Matches."}]
                    },
                    "image_validation": {
                        "field_checks": [{"field_name": "brand", "preserved": True, "reason": "Matches."}],
                        "overall_explanation": "All good.",
                    },
                }
            )
        ),
    )
    created = client.post(
        f"/api/slideshows/{slideshow_id}/generated-images/{generated_image_id}/validate"
    ).json()

    response = client.get(f"/api/slideshows/{slideshow_id}/generated-images/{generated_image_id}/validation")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
