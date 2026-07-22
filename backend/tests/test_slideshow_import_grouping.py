"""
Tests for POST /api/slideshows/import's group_as_one option (Phase 4.2 -
true multi-slide import, see MIGRATION_PLAN.md). Default (unset/False)
must remain provably unchanged - multi-file-select today means "N
independent Slideshows," a real, already-relied-on behavior; grouping is
opt-in only.
"""

import io
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

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


def _jpeg_bytes(color) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _three_files():
    return [
        ("files", ("first.jpg", io.BytesIO(_jpeg_bytes((200, 150, 90))), "image/jpeg")),
        ("files", ("second.jpg", io.BytesIO(_jpeg_bytes((90, 150, 200))), "image/jpeg")),
        ("files", ("third.jpg", io.BytesIO(_jpeg_bytes((150, 200, 90))), "image/jpeg")),
    ]


def test_default_import_creates_independent_slideshows(client):
    """The existing, relied-on behavior: unset group_as_one -> N separate Slideshows."""
    response = client.post("/api/slideshows/import", files=_three_files())

    assert response.status_code == 201
    slideshows = response.json()
    assert len(slideshows) == 3
    assert len({s["id"] for s in slideshows}) == 3
    for s in slideshows:
        assert len(s["slides"]) == 1
        assert s["slides"][0]["slide_index"] == 0


def test_explicit_false_matches_the_default(client):
    response = client.post(
        "/api/slideshows/import", files=_three_files(), data={"group_as_one": "false"}
    )
    assert response.status_code == 201
    assert len(response.json()) == 3


def test_group_as_one_creates_a_single_slideshow_with_ordered_slides(client):
    response = client.post(
        "/api/slideshows/import", files=_three_files(), data={"group_as_one": "true"}
    )

    assert response.status_code == 201
    slideshows = response.json()
    assert len(slideshows) == 1

    slideshow = slideshows[0]
    assert len(slideshow["slides"]) == 3
    assert [s["slide_index"] for s in slideshow["slides"]] == [0, 1, 2]
    assert [s["original_filename"] for s in slideshow["slides"]] == [
        "first.jpg",
        "second.jpg",
        "third.jpg",
    ]
    # Each Slide's own file was actually persisted, not just the DB rows.
    for slide in slideshow["slides"]:
        file_response = client.get(f"/api/slideshows/{slideshow['id']}/slides/{slide['id']}/file")
        assert file_response.status_code == 200


def test_group_as_one_with_a_single_file_behaves_like_a_normal_import(client):
    """Grouping one file is a degenerate case of itself - still a valid 1-Slide Slideshow."""
    response = client.post(
        "/api/slideshows/import",
        files=[("files", ("solo.jpg", io.BytesIO(_jpeg_bytes((10, 20, 30))), "image/jpeg"))],
        data={"group_as_one": "true"},
    )
    assert response.status_code == 201
    slideshows = response.json()
    assert len(slideshows) == 1
    assert len(slideshows[0]["slides"]) == 1
