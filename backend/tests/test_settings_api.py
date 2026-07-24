"""
API-level tests for /api/settings - Phase 12 (Human Feedback & Learning
System, see MIGRATION_PLAN.md). The AppSetting singleton row is lazily
created on first read/write - these tests confirm that, not just the
happy path of an already-existing row.
"""

import pytest
from fastapi.testclient import TestClient

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


def test_get_settings_lazily_creates_default_row(client):
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {"learning_mode_enabled": True}


def test_get_settings_returns_same_row_on_repeat_calls(client):
    first = client.get("/api/settings").json()
    second = client.get("/api/settings").json()

    assert first == second


def test_update_settings_disables_learning_mode(client):
    response = client.put("/api/settings", json={"learning_mode_enabled": False})

    assert response.status_code == 200
    assert response.json() == {"learning_mode_enabled": False}

    # Persisted - a fresh GET reflects the same value, not the default.
    assert client.get("/api/settings").json() == {"learning_mode_enabled": False}


def test_update_settings_re_enables_learning_mode(client):
    client.put("/api/settings", json={"learning_mode_enabled": False})

    response = client.put("/api/settings", json={"learning_mode_enabled": True})

    assert response.json() == {"learning_mode_enabled": True}
