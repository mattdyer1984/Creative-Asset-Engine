"""
API-level tests for the Phase 12 GenerationLog/archive wiring (see
MIGRATION_PLAN.md's "Human Feedback & Learning System") - confirms
generate-creative creates a real GenerationLog row and a real,
self-contained Generation Logs/{timestamp}/ folder on disk, not just
that the response shape changed. Reuses the same Fakes/pipeline-setup
helpers as test_generate_creative_api.py/test_generation_attempts_api.py
rather than duplicating them.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.generation_attempt import GenerationAttempt
from app.models.generation_log import GenerationLog
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


def test_generate_creative_creates_a_real_generation_log_and_archive(client, monkeypatch, db_session):
    slideshow_id, slide_id, product_id = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    _stub_a_winning_generate_creative_call(monkeypatch)

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert response.status_code == 201
    body = response.json()
    generation_log_id = body["generation_log_id"]
    assert generation_log_id

    generation_log = db_session.get(GenerationLog, generation_log_id)
    assert generation_log is not None
    assert generation_log.slideshow_id == slideshow_id
    assert generation_log.slide_id == slide_id
    assert generation_log.product_id == product_id
    assert generation_log.bundle_product_ids_json is None
    assert generation_log.winning_generated_image_id == body["winner"]["id"]
    assert generation_log.quality_mode == "fast"
    assert generation_log.creativity_level == "conservative"
    assert generation_log.retry_count == 0
    assert generation_log.generation_duration_seconds > 0
    assert generation_log.ai_provider is not None
    assert generation_log.ai_model is not None
    assert generation_log.prompt_used is not None

    # Every GenerationAttempt this call produced is linked back to the log.
    attempts = db_session.query(GenerationAttempt).filter(
        GenerationAttempt.generation_log_id == generation_log_id
    ).all()
    assert len(attempts) == 1

    # The real, self-contained archive folder on disk.
    archive_folder = settings.generation_logs_dir / generation_log.created_at.strftime("%Y-%m-%d_%H-%M-%S")
    assert str(archive_folder) == generation_log.archive_path
    assert archive_folder.is_dir()
    assert (archive_folder / "generated").is_dir()
    assert (archive_folder / "original").is_dir()
    assert (archive_folder / "references").is_dir()

    generated_files = list((archive_folder / "generated").iterdir())
    assert len(generated_files) == 1
    assert generated_files[0].name.startswith("slide_01")

    original_files = list((archive_folder / "original").iterdir())
    assert len(original_files) == 1
    assert original_files[0].name.startswith("slide_01")

    generation_json_path = archive_folder / "generation.json"
    assert generation_json_path.is_file()
    generation_json = json.loads(generation_json_path.read_text())
    assert generation_json["generation_uuid"] == generation_log_id
    assert generation_json["slideshow_id"] == slideshow_id
    assert generation_json["creative_id"] == slideshow_id  # no Creative entity post-Phase-2.8
    assert generation_json["product_id"] == product_id
    assert generation_json["retry_count"] == 0
    assert len(generation_json["generated_image_paths"]) == 1
    assert len(generation_json["original_image_paths"]) == 1

    # No review.json yet - nothing has reviewed this generation.
    assert not (archive_folder / "review.json").exists()


def test_generate_creative_archives_even_when_no_candidate_wins(client, monkeypatch, db_session):
    """
    A real, honest outcome (established throughout Phase 11.4/11.8) -
    the GenerationLog and archive must still be created, with an empty
    generated/ folder, not skipped.
    """
    slideshow_id, slide_id, product_id = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )
    failing_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": {
                "field_checks": [{"field_name": "silhouette", "preserved": False, "reason": "Wrong shape."}]
            },
        }
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=failing_vision),
    )
    monkeypatch.setattr(
        "app.services.creative_intelligence.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(
                result={"optimized_scene_description": "A staged product scene.", "reasoning": "Fake."}
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=failing_vision),
    )

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["winner"] is None

    generation_log = db_session.get(GenerationLog, body["generation_log_id"])
    assert generation_log is not None
    assert generation_log.winning_generated_image_id is None
    assert generation_log.ai_provider is None

    archive_folder = settings.generation_logs_dir / generation_log.created_at.strftime("%Y-%m-%d_%H-%M-%S")
    assert archive_folder.is_dir()
    assert list((archive_folder / "generated").iterdir()) == []
    generation_json = json.loads((archive_folder / "generation.json").read_text())
    assert generation_json["generated_image_paths"] == []
