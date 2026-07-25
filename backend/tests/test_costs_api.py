"""
API-level tests for GET /api/costs/daily (Optimisation & Stability Pass,
Tier 2.2, see MIGRATION_PLAN.md). Seeds AnalysisRun/GeneratedImage rows
directly rather than driving a real pipeline run - this endpoint is a
pure read-side aggregation, so it only needs rows with the right
columns set, not a real analysis history.
"""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.creative_specification import CreativeSpecification
from app.models.generated_image import GeneratedImage
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.stages.execution import mark_succeeded, start_analysis_run


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_analysis_run(db_session, slideshow, *, cost: float) -> None:
    analysis_run = start_analysis_run(
        db_session,
        slideshow_id=slideshow.id,
        analysis_type="marketing_analysis",
        provider="openai",
        model_name="gpt-5.5",
        durable=True,
    )
    mark_succeeded(db_session, analysis_run)
    analysis_run.estimated_cost_usd = cost
    db_session.commit()


def test_daily_costs_sums_analysis_runs(client, db_session, slideshow_with_slide):
    _seed_analysis_run(db_session, slideshow_with_slide, cost=0.01)
    _seed_analysis_run(db_session, slideshow_with_slide, cost=0.02)

    response = client.get("/api/costs/daily")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["analysis_cost_usd"] == pytest.approx(0.03)
    assert body[0]["call_count"] == 2
    assert body[0]["total_estimated_cost_usd"] == pytest.approx(0.03)


def test_daily_costs_includes_generated_image_cost(client, db_session, slideshow_with_slide):
    slide = slideshow_with_slide.primary_slide
    product = Product(display_name="Test Product")
    db_session.add(product)
    db_session.flush()

    def _dummy_analysis_run_id() -> str:
        run = start_analysis_run(
            db_session, analysis_type="ocr", provider="openai", model_name="gpt-5.5", durable=True
        )
        return run.id

    lock_profile = ProductLockProfile(
        analysis_run_id=_dummy_analysis_run_id(), product_id=product.id, structured_json={}
    )
    fingerprint = CreativeFingerprint(analysis_run_id=_dummy_analysis_run_id(), slide_id=slide.id, structured_json={})
    db_session.add(lock_profile)
    db_session.add(fingerprint)
    db_session.flush()

    creative_specification = CreativeSpecification(
        analysis_run_id=_dummy_analysis_run_id(),
        slideshow_id=slideshow_with_slide.id,
        slide_id=slide.id,
        product_lock_profile_id=lock_profile.id,
        creative_fingerprint_id=fingerprint.id,
        structured_json={},
    )
    db_session.add(creative_specification)
    db_session.flush()

    db_session.add(
        GeneratedImage(
            analysis_run_id=_dummy_analysis_run_id(),
            slideshow_id=slideshow_with_slide.id,
            slide_id=slide.id,
            creative_specification_id=creative_specification.id,
            is_current=False,
            provider="nano_banana",
            model_name="gemini-3.1-flash-image-preview",
            prompt_used="a prompt",
            seed=None,
            generation_time_seconds=1.0,
            file_path="/tmp/fake.png",
            estimated_cost_usd=0.05,
        )
    )
    db_session.commit()

    response = client.get("/api/costs/daily")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["image_generation_cost_usd"] == pytest.approx(0.05)


def test_daily_costs_returns_empty_list_with_no_data(client):
    response = client.get("/api/costs/daily")

    assert response.status_code == 200
    assert response.json() == []


def test_daily_costs_zero_when_no_pricing_configured(client, db_session, slideshow_with_slide):
    """A call with no configured rate still counts (call_count), but contributes $0, per the schema's own docstring."""
    analysis_run = start_analysis_run(
        db_session,
        slideshow_id=slideshow_with_slide.id,
        analysis_type="ocr",
        provider="openai",
        model_name="gpt-5.5",
        durable=True,
    )
    mark_succeeded(db_session, analysis_run)  # no usage passed -> estimated_cost_usd stays None
    db_session.commit()

    response = client.get("/api/costs/daily")

    body = response.json()
    assert len(body) == 1
    assert body[0]["call_count"] == 1
    assert body[0]["analysis_cost_usd"] == 0.0
