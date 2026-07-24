"""
Router-level tests for POST /api/slideshows/import-url (Critical TikTok
Slideshow Import Fix, see MIGRATION_PLAN.md - no prior automated test
coverage existed for this endpoint at all, a real gap this fix closes
while it's already touching this endpoint's behavior). Mocks
app.routers.slideshows.import_tiktok_url directly - the orchestrator's
own logic (provider order, fallback, the integrity gate) already has
full coverage in test_tiktok_import_chain.py; these tests exercise only
this router's own wiring: default provider, validation, and exception-
to-HTTP-status mapping.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.importers.downie import DownieImportUnavailableError
from app.importers.playwright_tiktok import TikTokImportBlockedError, TikTokImportUnsupportedContentError
from app.main import app
from app.models.slideshow import Slideshow
from app.services.tiktok_import_chain import ImportIncompleteError


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _fake_slideshow(db_session) -> list[Slideshow]:
    slideshow = Slideshow(imported_at=datetime.now(timezone.utc), source_references_json={})
    db_session.add(slideshow)
    db_session.commit()
    db_session.refresh(slideshow)
    return [slideshow]


def test_import_url_defaults_to_auto_provider(monkeypatch, client, db_session):
    calls = []

    def _fake_import_tiktok_url(db, url, project_id, provider):
        calls.append(provider)
        return _fake_slideshow(db_session)

    monkeypatch.setattr("app.routers.slideshows.import_tiktok_url", _fake_import_tiktok_url)

    response = client.post("/api/slideshows/import-url", json={"url": "https://www.tiktok.com/@x/video/1"})

    assert response.status_code == 201
    assert calls == ["auto"]


def test_import_url_rejects_an_unknown_provider(client):
    response = client.post(
        "/api/slideshows/import-url",
        json={"url": "https://www.tiktok.com/@x/video/1", "provider": "not-a-real-provider"},
    )
    assert response.status_code == 400


def test_import_url_404s_for_an_unknown_project(client):
    response = client.post(
        "/api/slideshows/import-url",
        json={"url": "https://www.tiktok.com/@x/video/1", "project_id": "does-not-exist"},
    )
    assert response.status_code == 404


def test_import_url_maps_import_incomplete_error_to_422(monkeypatch, client):
    def _raise(*args, **kwargs):
        raise ImportIncompleteError("Slideshow import incomplete: expected 4 slides, downloaded 1.")

    monkeypatch.setattr("app.routers.slideshows.import_tiktok_url", _raise)

    response = client.post("/api/slideshows/import-url", json={"url": "https://www.tiktok.com/@x/video/1"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Slideshow import incomplete: expected 4 slides, downloaded 1."


def test_import_url_maps_blocked_error_to_503(monkeypatch, client):
    def _raise(*args, **kwargs):
        raise TikTokImportBlockedError("blocked")

    monkeypatch.setattr("app.routers.slideshows.import_tiktok_url", _raise)

    response = client.post("/api/slideshows/import-url", json={"url": "https://www.tiktok.com/@x/video/1"})
    assert response.status_code == 503


def test_import_url_maps_video_rejection_to_422(monkeypatch, client):
    def _raise(*args, **kwargs):
        raise TikTokImportUnsupportedContentError("video, not a slideshow")

    monkeypatch.setattr("app.routers.slideshows.import_tiktok_url", _raise)

    response = client.post("/api/slideshows/import-url", json={"url": "https://www.tiktok.com/@x/video/1"})
    assert response.status_code == 422


def test_import_url_maps_downie_unavailable_to_503(monkeypatch, client):
    def _raise(*args, **kwargs):
        raise DownieImportUnavailableError("not installed")

    monkeypatch.setattr("app.routers.slideshows.import_tiktok_url", _raise)

    response = client.post(
        "/api/slideshows/import-url",
        json={"url": "https://www.tiktok.com/@x/video/1", "provider": "downie"},
    )
    assert response.status_code == 503


def test_import_url_forwards_explicit_provider_choice(monkeypatch, client, db_session):
    calls = []

    def _fake_import_tiktok_url(db, url, project_id, provider):
        calls.append(provider)
        return _fake_slideshow(db_session)

    monkeypatch.setattr("app.routers.slideshows.import_tiktok_url", _fake_import_tiktok_url)

    response = client.post(
        "/api/slideshows/import-url",
        json={"url": "https://www.tiktok.com/@x/video/1", "provider": "downie"},
    )

    assert response.status_code == 201
    assert calls == ["downie"]
