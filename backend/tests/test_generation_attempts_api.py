"""
API-level tests for GET .../generation-attempts (Phase 11.2, see
MIGRATION_PLAN.md - a real, additive gap the Phase 11 audit found:
generate-creative's own response was the *only* place this data was
ever returned). Reuses the same Fakes/pipeline-setup helpers as
test_generate_creative_api.py rather than duplicating them.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.generated_image import GeneratedImage
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


def _stub_a_winning_generate_creative_call(monkeypatch):
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


def test_generation_attempts_404s_for_unknown_slideshow(client):
    response = client.get("/api/slideshows/does-not-exist/slides/also-fake/generation-attempts")
    assert response.status_code == 404


def test_generation_attempts_is_empty_before_any_generate_creative_call(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)

    response = client.get(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generation-attempts")

    assert response.status_code == 200
    assert response.json() == []


def test_generation_attempts_reflects_a_real_persisted_attempt(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    _stub_a_winning_generate_creative_call(monkeypatch)

    generate_response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert generate_response.status_code == 201
    winner_id = generate_response.json()["winner"]["id"]

    history_response = client.get(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generation-attempts")

    assert history_response.status_code == 200
    attempts = history_response.json()
    assert len(attempts) == 1
    assert len(attempts[0]["candidates"]) == 1
    candidate = attempts[0]["candidates"][0]
    assert candidate["generated_image"]["id"] == winner_id
    assert candidate["quality_assessment"]["accepted"] is True
    assert candidate["quality_assessment"]["photorealism"] == _PHOTOREALISM_PASSES


def test_generation_attempts_skips_a_candidate_with_no_quality_assessment(
    client, monkeypatch, db_session
):
    """
    Real bug, found live (not from a hypothesis): one real historical
    GeneratedImage row in the dev DB had no matching QualityAssessment
    at all - the Quality Engine call for it never persisted a result,
    in an earlier session, before this endpoint existed to read it
    back. A naive one-QualityAssessment-per-candidate assumption
    (`.one()`) 500'd on that real row the moment this endpoint was
    clicked through the actual UI. This locks the fix in place: skip
    a candidate with no assessment rather than crash the whole history.
    """
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    _stub_a_winning_generate_creative_call(monkeypatch)

    generate_response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    ).json()
    attempt_id = generate_response["attempts"][0]["id"]
    real_candidate = generate_response["attempts"][0]["candidates"][0]["generated_image"]

    # A second, real GeneratedImage row on the same attempt, deliberately
    # left without a QualityAssessment - reproducing the real orphaned
    # row found live, not a synthetic shape that could never occur.
    winning_image = db_session.get(GeneratedImage, real_candidate["id"])
    db_session.add(
        GeneratedImage(
            analysis_run_id=winning_image.analysis_run_id,
            slideshow_id=slideshow_id,
            slide_id=slide_id,
            creative_specification_id=winning_image.creative_specification_id,
            generation_attempt_id=attempt_id,
            candidate_index=1,
            provider="fake",
            model_name="fake-model",
            prompt_used="orphaned candidate, no quality assessment",
            generation_time_seconds=1.0,
            file_path="/tmp/orphan.png",
        )
    )
    db_session.commit()

    response = client.get(f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generation-attempts")

    assert response.status_code == 200
    attempts = response.json()
    assert len(attempts) == 1
    # Only the real, scored candidate is returned - the orphaned one is
    # skipped, not crashed on.
    assert len(attempts[0]["candidates"]) == 1
    assert attempts[0]["candidates"][0]["generated_image"]["id"] == real_candidate["id"]


def test_generation_attempts_orders_most_recent_first(client, monkeypatch, db_session):
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    _stub_a_winning_generate_creative_call(monkeypatch)

    first = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    ).json()
    second = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    ).json()

    attempts = client.get(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generation-attempts"
    ).json()

    assert len(attempts) == 2
    assert attempts[0]["id"] == second["attempts"][0]["id"]
    assert attempts[1]["id"] == first["attempts"][0]["id"]
