"""
API-level tests for POST .../generate-creative (Phase 10.2 of AI
Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §11-§14). No real provider calls - Fakes throughout,
same discipline as test_generated_image_api.py, whose pipeline-setup
helper this file reuses rather than duplicating.
"""

import io

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


def test_generate_creative_404s_for_unknown_slideshow(client):
    response = client.post(
        "/api/slideshows/does-not-exist/slides/also-fake/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert response.status_code == 404


def test_generate_creative_404s_for_an_unknown_slide_id(client):
    """
    Real-world-diagnosed change (Generate All, see MIGRATION_PLAN.md):
    generate-creative is no longer restricted to the primary slide - a
    slide id that doesn't exist at all is the real 404 case now, not
    "any slide other than the primary."
    """
    slideshow_id, _, _ = _import_slideshow_with_product(client)
    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/does-not-exist/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert response.status_code == 404


def test_generate_creative_404s_for_a_slide_from_a_different_slideshow(client):
    slideshow_id, _, _ = _import_slideshow_with_product(client)
    other_slideshow_id, other_slide_id, _ = _import_slideshow_with_product(client)

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{other_slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    )
    assert response.status_code == 404


def _import_slideshow_with_two_products(client) -> tuple[str, str, str, str, str]:
    """
    Returns (slideshow_id, primary_slide_id, primary_product_id,
    second_slide_id, second_product_id) - two slides in one grouped
    slideshow, each assigned a genuinely different product, exactly the
    shape Generate All produces and the real bug this fix targets (see
    MIGRATION_PLAN.md).
    """
    from io import BytesIO

    from PIL import Image

    product_a = client.post("/api/products", json={"display_name": "Product A"}).json()
    product_b = client.post("/api/products", json={"display_name": "Product B"}).json()

    def _jpeg_bytes(color):
        buffer = BytesIO()
        Image.new("RGB", (300, 300), color=color).save(buffer, format="JPEG")
        return buffer.getvalue()

    slideshows = client.post(
        "/api/slideshows/import",
        files=[
            ("files", ("slide-a.jpg", io.BytesIO(_jpeg_bytes((210, 160, 120))), "image/jpeg")),
            ("files", ("slide-b.jpg", io.BytesIO(_jpeg_bytes((80, 130, 200))), "image/jpeg")),
        ],
        data={"group_as_one": "true"},
    ).json()
    slideshow = slideshows[0]
    slide_a_id = slideshow["slides"][0]["id"]
    slide_b_id = slideshow["slides"][1]["id"]

    client.post(
        f"/api/slideshows/{slideshow['id']}/slides/{slide_a_id}/assign-product",
        json={"product_id": product_a["id"]},
    )
    client.post(
        f"/api/slideshows/{slideshow['id']}/slides/{slide_b_id}/assign-product",
        json={"product_id": product_b["id"]},
    )
    return slideshow["id"], slide_a_id, product_a["id"], slide_b_id, product_b["id"]


def test_generate_creative_succeeds_for_a_non_primary_slide_with_its_own_product(
    client, monkeypatch, db_session
):
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): the exact scenario
    Generate All produces - two slides, two different products, one
    shared CreativeSpecification built from the primary slide alone.
    Generating for the *second* slide must validate against *that
    slide's own* product, not silently succeed-or-fail against the
    primary slide's product (the bug §0 fixed in
    image_validation_stage.py's _resolve_product).
    """
    slideshow_id, _, _, slide_b_id, product_b_id = _import_slideshow_with_two_products(client)
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
    monkeypatch.setattr(
        "app.services.creative_intelligence.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(
                result={"optimized_scene_description": "A staged product scene.", "reasoning": "Fake."}
            )
        ),
    )

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_b_id}/generate-creative",
        json={"quality_mode": "fast"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["winner"] is not None
    candidate = body["attempts"][0]["candidates"][0]
    assert candidate["quality_assessment"]["accepted"] is True

    # The generated image and its GenerationLog are stamped to slide B,
    # not the primary slide - product_b_id used only to document intent.
    log = client.get(f"/api/generation-logs/{body['generation_log_id']}").json()
    assert log["slide_id"] == slide_b_id
    assert log["product_id"] == product_b_id


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


def test_generate_creative_returns_structured_500_on_unexpected_exception(client, monkeypatch, db_session):
    """
    Tier 1.3 reliability fix: generate_with_retry has no internal
    try/except of its own (see its module docstring) - before this fix,
    anything beyond the already-handled ValueError case (a genuine bug,
    an unhandled provider error shape) surfaced as FastAPI's generic,
    undifferentiated 500 with no useful detail. This is synchronous, so
    nothing is left "stuck" either way, but the error should now at
    least be explained.
    """
    slideshow_id, slide_id, _ = _import_slideshow_with_product(client)
    _run_full_pipeline_through_creative_specification(client, slideshow_id, monkeypatch, db_session)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated genuine bug inside the retry loop")

    monkeypatch.setattr("app.routers.slideshows.generate_with_retry", _boom)

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/generate-creative",
        json={"quality_mode": "fast"},
    )

    assert response.status_code == 500
    assert "simulated genuine bug inside the retry loop" in response.json()["detail"]


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
