"""
API-level tests for POST .../generate-creative (Phase 10.2 of AI
Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §11-§14). No real provider calls - Fakes throughout,
same discipline as test_generated_image_api.py, whose pipeline-setup
helper this file reuses rather than duplicating.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider, FakeVisionAnalysisProvider
from tests.test_generated_image_api import _import_slideshow_with_product, _run_full_pipeline_through_creative_specification

_IDENTITY_PASSES = {"field_checks": [{"field_name": "silhouette", "preserved": True, "reason": "Matches."}]}
_CREATIVE_PASSES = {
    "field_checks": [{"field_name": "color", "preserved": True, "reason": "Matches."}],
    "overall_explanation": "Everything preserved.",
}
_PHOTOREALISM_PASSES = {
    "realistic_lighting": True,
    "believable_shadows": True,
    "material_accuracy": True,
    "reflections_correct": True,
    "texture_quality": "excellent",
    "perspective_correct": True,
    "object_integrity": True,
    "human_anatomy": "not_applicable",
    "ai_artefacts_detected": False,
    "image_sharpness": "excellent",
    "reasons": ["clean, photorealistic render"],
}


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_generate_creative_404s_for_unknown_slideshow(client):
    response = client.post(
        "/api/slideshows/does-not-exist/slides/also-fake/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert response.status_code == 404


def test_generate_creative_400s_for_a_non_primary_slide_id(client):
    slideshow_id, _, _ = _import_slideshow_with_product(client)
    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/not-the-primary-slide/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert response.status_code == 400


def test_generate_creative_422s_for_an_unknown_quality_mode(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "ludicrous"},
    )

    assert response.status_code == 422


def test_generate_creative_succeeds_and_returns_the_winner(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )
    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": _CREATIVE_PASSES,
            "photorealism": _PHOTOREALISM_PASSES,
        }
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["attempts"]) == 1
    assert len(body["attempts"][0]["candidates"]) == 1
    candidate = body["attempts"][0]["candidates"][0]
    assert candidate["quality_assessment"]["accepted"] is True
    assert candidate["quality_assessment"]["photorealism"] == _PHOTOREALISM_PASSES
    assert body["winner"] is not None
    assert body["winner"]["id"] == candidate["generated_image"]["id"]

    # The winner is also servable as "the" current generated image,
    # same endpoint the Phase 8.3 single-call path already uses.
    current = client.get(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generated-image")
    assert current.status_code == 200
    assert current.json()["id"] == body["winner"]["id"]
