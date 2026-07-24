"""
API-level tests for the Phase 9.2 reference-library/score-references
endpoints (see MIGRATION_PLAN.md's "ADR: Canonical Product Reference"
§8). The scoring stage itself is covered by
tests/test_reference_scoring_stage.py - these tests are endpoint-wiring
smoke tests, not a second copy of that coverage, so the background
scoring call is monkeypatched to a no-op.
"""

import pytest
from fastapi.testclient import TestClient

import app.routers.products as products_router
from app.db import get_db
from app.main import app


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_score_references_returns_404_for_unknown_product(client):
    response = client.post("/api/products/does-not-exist/score-references")
    assert response.status_code == 404


def test_score_references_schedules_and_returns_202(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        products_router, "run_reference_scoring_in_background", lambda product_id: calls.append(product_id)
    )

    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    response = client.post(f"/api/products/{product['id']}/score-references")

    assert response.status_code == 202
    assert calls == [product["id"]]


def test_reference_library_returns_only_included_images(client, db_session, tmp_path):
    from io import BytesIO

    from PIL import Image

    from app.models.product_reference_image import ProductReferenceImage

    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()

    def _make_reference_image(*, library_status):
        buffer = BytesIO()
        Image.new("RGB", (300, 300), color=(210, 160, 120)).save(buffer, format="JPEG")
        path = tmp_path / f"{library_status}.jpg"
        path.write_bytes(buffer.getvalue())
        image = ProductReferenceImage(
            product_id=product["id"],
            file_path=str(path),
            isolation_method="product_url",
            library_status=library_status,
            role="front" if library_status == "included" else None,
            quality_score=0.9 if library_status == "included" else 0.1,
        )
        db_session.add(image)
        return image

    _make_reference_image(library_status="included")
    _make_reference_image(library_status="rejected")
    db_session.commit()

    response = client.get(f"/api/products/{product['id']}/reference-library")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["library_status"] == "included"
    assert body[0]["role"] == "front"


# --- Phase 9.6 of Product Lock v2 (see MIGRATION_PLAN.md's ADR §4/§8) -
# user upload path + the human-in-the-loop library-status override. ---


def test_upload_reference_image_404s_for_unknown_product(client):
    response = client.post(
        "/api/products/does-not-exist/reference-images/upload",
        files={"file": ("ref.jpg", b"not-really-a-jpeg", "image/jpeg")},
    )
    assert response.status_code == 404


def test_upload_reference_image_creates_an_unscored_candidate(client):
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()

    response = client.post(
        f"/api/products/{product['id']}/reference-images/upload",
        files={"file": ("ref.jpg", b"not-really-a-jpeg-but-thats-fine-here", "image/jpeg")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["library_status"] is None  # a real, ordinary unscored candidate
    assert body["is_current"] is True

    # Not yet in the compute-on-read Library - it hasn't been scored yet.
    library = client.get(f"/api/products/{product['id']}/reference-library").json()
    assert library == []


def test_update_library_status_404s_for_unknown_image(client):
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    response = client.post(
        f"/api/products/{product['id']}/reference-images/does-not-exist/library-status",
        json={"status": "rejected"},
    )
    assert response.status_code == 404


def test_update_library_status_422s_for_an_invalid_status(client):
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    uploaded = client.post(
        f"/api/products/{product['id']}/reference-images/upload",
        files={"file": ("ref.jpg", b"some-bytes", "image/jpeg")},
    ).json()

    response = client.post(
        f"/api/products/{product['id']}/reference-images/{uploaded['id']}/library-status",
        json={"status": "not-a-real-status"},
    )

    assert response.status_code == 422


def test_update_library_status_lets_a_user_manually_include_an_image(client):
    """
    The human-in-the-loop override the ADR requires - a user can include
    an image directly rather than waiting for/trusting the automatic
    score, and this is also how a user confirms a non-blocking upgrade
    prompt (§9): "supersede the old one" is exactly a manual write of
    library_status="superseded" on the old image.
    """
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    uploaded = client.post(
        f"/api/products/{product['id']}/reference-images/upload",
        files={"file": ("ref.jpg", b"some-bytes", "image/jpeg")},
    ).json()

    response = client.post(
        f"/api/products/{product['id']}/reference-images/{uploaded['id']}/library-status",
        json={"status": "included"},
    )

    assert response.status_code == 200
    assert response.json()["library_status"] == "included"

    library = client.get(f"/api/products/{product['id']}/reference-library").json()
    assert [image["id"] for image in library] == [uploaded["id"]]


# --- Phase 11.5 (frontend consolidation, see MIGRATION_PLAN.md) - the
# human-in-the-loop override on role, mirroring library-status. ---


def test_update_role_404s_for_unknown_image(client):
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    response = client.post(
        f"/api/products/{product['id']}/reference-images/does-not-exist/role",
        json={"role": "front"},
    )
    assert response.status_code == 404


def test_update_role_lets_a_user_manually_set_role(client):
    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    uploaded = client.post(
        f"/api/products/{product['id']}/reference-images/upload",
        files={"file": ("ref.jpg", b"some-bytes", "image/jpeg")},
    ).json()
    assert uploaded["role"] is None  # a real, ordinary unscored candidate has no role yet

    response = client.post(
        f"/api/products/{product['id']}/reference-images/{uploaded['id']}/role",
        json={"role": "packaging"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "packaging"
