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
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.evidence_source import EVIDENCE_TYPE_SLIDESHOW_UPLOAD, EvidenceSource
from app.models.slideshow import Slideshow


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


def test_import_records_one_evidence_source_shared_by_every_independent_slideshow(
    client, db_session
):
    """Phase 10.5: default (non-grouped) import still routes through the Evidence Engine -
    one EvidenceSource per Import Provider call, shared by every Slideshow it produces."""
    response = client.post("/api/slideshows/import", files=_three_files())
    assert response.status_code == 201
    slideshow_ids = [s["id"] for s in response.json()]

    evidence_sources = list(db_session.scalars(select(EvidenceSource)))
    assert len(evidence_sources) == 1
    assert evidence_sources[0].source_platform == "local_file"
    assert evidence_sources[0].evidence_type == EVIDENCE_TYPE_SLIDESHOW_UPLOAD

    slideshows = list(db_session.scalars(select(Slideshow).where(Slideshow.id.in_(slideshow_ids))))
    assert len(slideshows) == 3
    assert all(s.evidence_source_id == evidence_sources[0].id for s in slideshows)


def test_group_as_one_import_records_one_evidence_source(client, db_session):
    response = client.post(
        "/api/slideshows/import", files=_three_files(), data={"group_as_one": "true"}
    )
    assert response.status_code == 201
    slideshow_id = response.json()[0]["id"]

    evidence_sources = list(db_session.scalars(select(EvidenceSource)))
    assert len(evidence_sources) == 1

    slideshow = db_session.get(Slideshow, slideshow_id)
    assert slideshow.evidence_source_id == evidence_sources[0].id
