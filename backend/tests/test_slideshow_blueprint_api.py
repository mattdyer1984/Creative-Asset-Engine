"""
API-level tests for the /api/slideshows/* surface. Originally written in
Phase 2.5 of the Slideshow/Slide migration to mirror
tests/test_creative_blueprint_api.py's coverage of the old
/api/creatives/* surface (removed in Phase 2.7, along with that test
file); the product-assignment tests below were moved here from
test_products_api.py in Phase 2.7 for the same reason.
"""

import io
import threading

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.analysis_run import ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE
from app.models.product_lock_profile import ProductLockProfile
from app.stages.execution import start_analysis_run
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
    assert len(slide["products"]) == 1
    assert slide["products"][0]["product_lock_profile"] is None
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


def test_rerun_returns_202_and_queued_immediately(client, monkeypatch):
    """
    POST .../rerun (Phase 3.3 - async execution boundary, see
    MIGRATION_PLAN.md) mirrors /analyze: schedules the stage in the
    background and returns as soon as status flips to "queued" - content
    assertions belong on a separate GET /blueprint call, see the next two
    tests.
    """
    slideshow_id, _, _ = _import_slideshow_with_product(client)
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    response = client.post(f"/api/slideshows/{slideshow_id}/stages/ocr/rerun")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_rerun_rejects_a_second_trigger_while_in_progress(client):
    """Same new failure mode as /analyze (Phase 3.3) - see the equivalent /analyze test."""
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    from app.db import SessionLocal
    from app.models.slideshow import STATUS_ANALYZING, Slideshow

    db = SessionLocal()
    slideshow = db.get(Slideshow, slideshow_id)
    slideshow.status = STATUS_ANALYZING
    db.commit()
    db.close()

    response = client.post(f"/api/slideshows/{slideshow_id}/stages/ocr/rerun")
    assert response.status_code == 409


def test_rerun_atomically_claims_the_row_under_real_concurrency(client):
    """Same real bug/fix as analyze's equivalent test (Phase 3.3 shares the exact same claim logic)."""
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    import app.db
    from app.routers.slideshows import rerun_stage

    results = []
    barrier = threading.Barrier(2)

    def call():
        db = app.db.SessionLocal()
        try:
            barrier.wait()
            try:
                rerun_stage(slideshow_id, "ocr", BackgroundTasks(), db=db)
                results.append(202)
            except HTTPException as exc:
                results.append(exc.status_code)
        finally:
            db.close()

    threads = [threading.Thread(target=call) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [202, 409]


def test_rerun_ocr_populates_blueprint_and_returns_it(client, monkeypatch):
    slideshow_id, _, _ = _import_slideshow_with_product(client)

    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    client.post(f"/api/slideshows/{slideshow_id}/stages/ocr/rerun")
    body = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()

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
    client.post(f"/api/slideshows/{slideshow_id}/stages/recreation_prompt/rerun")
    body = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()

    assert body["status"] == "failed"
    assert body["failed_stage"] == "recreation_prompt"
    assert "No Product Lock Profile" in body["failed_stage_error"]
    assert body["recreation_prompt"] is None


def test_analyze_returns_202_and_queued_immediately(client, monkeypatch):
    """
    POST /analyze (Phase 3.2 - async execution boundary, see
    MIGRATION_PLAN.md) schedules the pipeline in the background and
    returns as soon as status flips to "queued" - the response body
    reflects that pre-background-run state (verified: FastAPI serializes
    the response_model before BackgroundTasks run), not the pipeline's
    eventual outcome. Content assertions belong on a separate GET
    /blueprint call - see the next two tests.
    """
    slideshow_id = _import_slideshow(client)
    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    response = client.post(f"/api/slideshows/{slideshow_id}/analyze")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_analyze_rejects_a_second_trigger_while_in_progress(client):
    """
    New failure mode introduced by going async (Phase 3.2): two overlapping
    /analyze calls used to be impossible (the first request's own thread
    was the lock). Directly setting status to simulate "already running",
    since TestClient's synchronous background-task execution means a real
    race can't be reproduced through the HTTP layer in a test.
    """
    slideshow_id = _import_slideshow(client)

    from app.db import SessionLocal
    from app.models.slideshow import STATUS_ANALYZING, Slideshow

    db = SessionLocal()
    slideshow = db.get(Slideshow, slideshow_id)
    slideshow.status = STATUS_ANALYZING
    db.commit()
    db.close()

    response = client.post(f"/api/slideshows/{slideshow_id}/analyze")
    assert response.status_code == 409


def test_analyze_atomically_claims_the_row_under_real_concurrency(client):
    """
    Reproduces, deterministically, a real bug a live test against an
    actual running server (not just TestClient) caught: the first version
    of /analyze's guard was a plain read-then-write (read status, check
    it, then set status=queued and commit) - two genuinely concurrent
    requests could both read the pre-queued status before either had
    committed, so both would pass the guard and both get 202.

    Deliberately does NOT go through the `client` fixture's shared
    db_session for the concurrent calls themselves - the fixture's
    override_get_db always yields that one shared Session object, which
    isn't safe to call from two threads at once and wouldn't reproduce
    the actual bug anyway (production's real race is between two
    independent Sessions/connections against the same SQLite file, via
    app.db.SessionLocal per-request - see app.db.get_db). Calls the route
    function directly with its own Session per thread instead, which
    faithfully reproduces that shape.
    """
    slideshow_id = _import_slideshow(client)

    import app.db
    from app.routers.slideshows import analyze_slideshow

    results = []
    barrier = threading.Barrier(2)

    def call():
        db = app.db.SessionLocal()
        try:
            barrier.wait()
            try:
                analyze_slideshow(slideshow_id, BackgroundTasks(), db=db)
                results.append(202)
            except HTTPException as exc:
                results.append(exc.status_code)
        finally:
            db.close()

    threads = [threading.Thread(target=call) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [202, 409]


def test_analyze_surfaces_prerequisite_failure_with_no_product_assigned(client, monkeypatch):
    """
    Importing a slideshow and clicking Analyze WITHOUT assigning a
    product first: OCR succeeds, then Product Isolation fails its
    prerequisite check before creating any AnalysisRun - a subsequent GET
    /blueprint must name exactly what failed (the POST /analyze response
    itself no longer carries analysis content - see
    test_analyze_returns_202_and_queued_immediately).
    """
    slideshow_id = _import_slideshow(client)
    # Deliberately no assign-product call.

    monkeypatch.setattr("app.slideshow_stages.ocr_stage.default_registry", FakeAIProviderRegistry())

    client.post(f"/api/slideshows/{slideshow_id}/analyze")
    body = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()

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
    # Narrative Structure (Phase 7.2) shares TextGenerationProvider with
    # Marketing Analysis but expects a different response shape - its own
    # fake registry, not the shared-shape one above.
    monkeypatch.setattr(
        "app.slideshow_stages.narrative_structure_stage.default_registry",
        FakeAIProviderRegistry(
            text_generation_provider=FakeTextGenerationProvider(
                result={"slides": [{"slide_index": 0, "beat": "hook"}], "arc_summary": "A short arc."}
            )
        ),
    )
    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    response = client.post(f"/api/slideshows/{slideshow_id}/analyze")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    blueprint = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    assert blueprint["status"] == "ready"
    slide = blueprint["slides"][0]
    assert slide["ocr_result"] is not None
    assert len(slide["products"]) == 1
    product = slide["products"][0]
    assert len(product["product_reference_images"]) == 1
    assert product["product_lock_profile"] is not None
    assert slide["creative_fingerprint"] is not None
    assert blueprint["marketing_analysis"] is not None
    assert blueprint["narrative_structure"] is not None
    assert blueprint["narrative_structure"]["structured"]["slides"] == [
        {"slide_id": slide["id"], "slide_index": 0, "beat": "hook"}
    ]
    assert blueprint["narrative_structure"]["structured"]["arc_summary"] == "A short arc."
    assert blueprint["recreation_prompt"] is not None
    assert blueprint["recreation_prompt"]["structured"]["product_lock_reference"][
        "product_lock_profile_id"
    ] == product["product_lock_profile"]["id"]


def test_blueprint_regroups_artifacts_per_product_on_a_multi_product_slide(client, db_session):
    """
    Phase 6.4: the actual point of the regrouping - a slide with 2
    distinct current products must surface each product's own Lock
    Profile, not just the first one silently (the old flat
    product_lock_profile field only ever showed current_appearances[0]'s
    data). Lock Profiles are persisted directly rather than via the
    stage, since Phase 6.2 made the stage itself reject multi-product
    slides.
    """
    slideshow_id, slide_id, product_a_id = _import_slideshow_with_product(client)
    product_b_id = client.post("/api/products", json={"display_name": "Second Product"}).json()["id"]
    client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/products",
        json={"product_id": product_b_id},
    )

    def _make_lock_profile(product_id, category):
        analysis_run = start_analysis_run(
            db_session,
            analysis_type=ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE,
            provider="fake",
            model_name="fake",
            durable=False,
        )
        profile = ProductLockProfile(
            analysis_run_id=analysis_run.id,
            product_id=product_id,
            structured_json={"product_category": category},
            reference_image_ids_json=[],
        )
        db_session.add(profile)
        db_session.commit()
        return profile

    profile_a = _make_lock_profile(product_a_id, "product-a-category")
    profile_b = _make_lock_profile(product_b_id, "product-b-category")

    body = client.get(f"/api/slideshows/{slideshow_id}/blueprint").json()
    products = body["slides"][0]["products"]
    assert len(products) == 2

    by_product_id = {p["appearance"]["product_id"]: p for p in products}
    assert by_product_id[product_a_id]["product_lock_profile"]["id"] == profile_a.id
    assert by_product_id[product_a_id]["product_lock_profile"]["structured"]["product_category"] == "product-a-category"
    assert by_product_id[product_b_id]["product_lock_profile"]["id"] == profile_b.id
    assert by_product_id[product_b_id]["product_lock_profile"]["structured"]["product_category"] == "product-b-category"


def test_assign_and_unassign_product_on_slide(client):
    """
    New-pipeline equivalent of the old
    test_assign_and_unassign_product_on_creative (moved from
    test_products_api.py in Phase 2.7 along with the old endpoint it
    tested) - assignment now creates/flips a ProductAppearance on a
    Slide instead of setting Creative.product_id directly.
    """
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    slideshow_id = _import_slideshow(client)
    slide = client.get(f"/api/slideshows/{slideshow_id}").json()["slides"][0]
    assert slide["current_product_appearance"] is None

    assign_response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide['id']}/assign-product",
        json={"product_id": product["id"]},
    )
    assert assign_response.status_code == 200
    assigned_slide = assign_response.json()["slides"][0]
    assert assigned_slide["current_product_appearance"]["product_id"] == product["id"]
    assert assigned_slide["current_product_appearance"]["product"]["display_name"] == "Sunrise Orange Juice"

    unassign_response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide['id']}/assign-product",
        json={"product_id": None},
    )
    assert unassign_response.json()["slides"][0]["current_product_appearance"] is None


def test_assigning_unknown_product_404s(client):
    """New-pipeline equivalent of the old test of the same name, moved from test_products_api.py."""
    slideshow_id = _import_slideshow(client)
    slide_id = client.get(f"/api/slideshows/{slideshow_id}").json()["slides"][0]["id"]

    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/{slide_id}/assign-product",
        json={"product_id": "does-not-exist"},
    )
    assert response.status_code == 404


def test_assigning_product_to_unknown_slide_404s(client):
    slideshow_id = _import_slideshow(client)
    response = client.post(
        f"/api/slideshows/{slideshow_id}/slides/does-not-exist/assign-product",
        json={"product_id": None},
    )
    assert response.status_code == 404
