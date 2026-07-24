"""
API-level tests for /api/generation-logs/* - Phase 12 (Human Feedback &
Learning System, see MIGRATION_PLAN.md). Reuses the same Fakes/pipeline
helpers as test_generation_log_archive.py rather than duplicating them.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from tests.fakes import (
    FakeAIProviderRegistry,
    FakeImageGenerationProvider,
    FakeTextGenerationProvider,
    FakeVisionAnalysisProvider,
)
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


def _create_a_real_generation_log(client, monkeypatch, db_session) -> tuple[str, str]:
    """Returns (generation_log_id, product_id)."""
    slideshow_id, slide_id, product_id = _import_slideshow_with_product(client)
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
    # Phase 10.4 (Creative Intelligence, see MIGRATION_PLAN.md) - a real,
    # pre-existing gap found while building Phase 12: creative_intelligence.py
    # imports its own default_registry independently of
    # generation_engine's, so patching that one alone doesn't stop this
    # real, paid text-generation call whenever a SceneAnalysis exists.
    monkeypatch.setattr(
        "app.services.creative_intelligence.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(
                result={"optimized_scene_description": "A staged product scene.", "reasoning": "Fake."}
            )
        ),
    )

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    )
    return response.json()["generation_log_id"], product_id


# --- GET /api/generation-logs/{id} -------------------------------------


def test_get_generation_log_unknown_404s(client):
    response = client.get("/api/generation-logs/does-not-exist")
    assert response.status_code == 404


def test_get_generation_log_has_no_review_before_one_is_submitted(client, monkeypatch, db_session):
    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)

    response = client.get(f"/api/generation-logs/{generation_log_id}")

    assert response.status_code == 200
    assert response.json()["review"] is None


# --- GET /api/generation-logs (list) ------------------------------------


def test_list_generation_logs_returns_created_logs_most_recent_first(client, monkeypatch, db_session):
    first_id, product_id = _create_a_real_generation_log(client, monkeypatch, db_session)
    second_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)

    response = client.get("/api/generation-logs")

    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert ids.index(second_id) < ids.index(first_id)


def test_list_generation_logs_filters_by_product_id(client, monkeypatch, db_session):
    generation_log_id, product_id = _create_a_real_generation_log(client, monkeypatch, db_session)

    response = client.get(f"/api/generation-logs?product_id={product_id}")

    assert response.status_code == 200
    assert all(row["product_id"] == product_id for row in response.json())
    assert generation_log_id in [row["id"] for row in response.json()]


def test_list_generation_logs_sorts_by_score(client, monkeypatch, db_session):
    low_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)
    high_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)
    client.post(f"/api/generation-logs/{low_id}/review", json={"overall_score": 20, "main_issue": "lighting"})
    client.post(f"/api/generation-logs/{high_id}/review", json={"overall_score": 90, "main_issue": "none"})

    response = client.get("/api/generation-logs?sort=score_desc")

    ids = [row["id"] for row in response.json()]
    assert ids.index(high_id) < ids.index(low_id)


# --- POST /api/generation-logs/{id}/review ------------------------------


def test_create_review_unknown_generation_log_404s(client):
    response = client.post(
        "/api/generation-logs/does-not-exist/review",
        json={"overall_score": 80, "main_issue": "none"},
    )
    assert response.status_code == 404


def test_create_review_rejects_an_invalid_main_issue(client, monkeypatch, db_session):
    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)

    response = client.post(
        f"/api/generation-logs/{generation_log_id}/review",
        json={"overall_score": 80, "main_issue": "not-a-real-issue"},
    )

    assert response.status_code == 422


def test_create_review_rejects_a_score_outside_0_100(client, monkeypatch, db_session):
    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)

    response = client.post(
        f"/api/generation-logs/{generation_log_id}/review",
        json={"overall_score": 150, "main_issue": "none"},
    )

    assert response.status_code == 422


def test_create_review_succeeds_and_persists_permanently(client, monkeypatch, db_session):
    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)

    response = client.post(
        f"/api/generation-logs/{generation_log_id}/review",
        json={"overall_score": 72, "main_issue": "composition", "comment": "Product slightly too small."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_score"] == 72
    assert body["main_issue"] == "composition"
    assert body["comment"] == "Product slightly too small."
    assert body["learning_mode_enabled"] is True  # default AppSetting state

    # Permanently linked - a fresh GET reflects the same review.
    detail = client.get(f"/api/generation-logs/{generation_log_id}").json()
    assert detail["review"]["overall_score"] == 72


def test_create_review_writes_a_real_review_json_into_the_archive(client, monkeypatch, db_session):
    import json

    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)
    archive_path = client.get(f"/api/generation-logs/{generation_log_id}").json()["archive_path"]

    client.post(
        f"/api/generation-logs/{generation_log_id}/review",
        json={"overall_score": 55, "main_issue": "text", "comment": None},
    )

    from pathlib import Path

    review_json = json.loads((Path(archive_path) / "review.json").read_text())
    assert review_json["generation_uuid"] == generation_log_id
    assert review_json["overall_score"] == 55
    assert review_json["main_issue"] == "text"


def test_create_review_rejects_a_second_review_for_the_same_log(client, monkeypatch, db_session):
    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)
    client.post(
        f"/api/generation-logs/{generation_log_id}/review",
        json={"overall_score": 60, "main_issue": "none"},
    )

    response = client.post(
        f"/api/generation-logs/{generation_log_id}/review",
        json={"overall_score": 90, "main_issue": "none"},
    )

    assert response.status_code == 400


def test_create_review_snapshots_learning_mode_disabled(client, monkeypatch, db_session):
    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)
    client.put("/api/settings", json={"learning_mode_enabled": False})

    response = client.post(
        f"/api/generation-logs/{generation_log_id}/review",
        json={"overall_score": 40, "main_issue": "realism"},
    )

    assert response.json()["learning_mode_enabled"] is False


# --- GET /api/generation-logs/{id}/download-zip -------------------------


def test_download_zip_unknown_generation_log_404s(client):
    response = client.get("/api/generation-logs/does-not-exist/download-zip")
    assert response.status_code == 404


def test_download_zip_contains_only_the_generated_images(client, monkeypatch, db_session):
    import io
    import zipfile

    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)

    response = client.get(f"/api/generation-logs/{generation_log_id}/download-zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    names = zip_file.namelist()
    # Only the publish-ready image(s) - no generation.json/review.json.
    assert len(names) == 1
    assert names[0].startswith("slide_01")
    assert not any(name.endswith(".json") for name in names)


# --- POST /api/generation-logs/{id}/open-folder --------------------------


def test_open_folder_unknown_generation_log_404s(client):
    response = client.post("/api/generation-logs/does-not-exist/open-folder")
    assert response.status_code == 404


def test_open_folder_shells_out_to_open_with_the_archive_path(client, monkeypatch, db_session):
    generation_log_id, _ = _create_a_real_generation_log(client, monkeypatch, db_session)
    archive_path = client.get(f"/api/generation-logs/{generation_log_id}").json()["archive_path"]

    calls = []
    monkeypatch.setattr(
        "app.routers.generation_logs.subprocess.run",
        lambda args, **kwargs: calls.append(args),
    )

    response = client.post(f"/api/generation-logs/{generation_log_id}/open-folder")

    assert response.status_code == 204
    assert calls == [["open", archive_path]]
