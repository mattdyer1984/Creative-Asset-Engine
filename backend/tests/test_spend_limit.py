"""
Spend cap tests (Phase 1 remediation, WP-5).

Properties that matter: it guards only NEW paid work, in-flight work is
never interrupted, the boundary is the LOCAL day, and the 429 tells the
caller everything they need to act on.
"""

from datetime import datetime, timedelta

import pytest

from app.models.provider_call import RECORD_SOURCE_PER_CALL, ProviderCall
from app.services.cost_estimation import CostStatus
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services.spend_limit import (
    PlannedCall,
    SpendLimitExceeded,
    UnpricedWorkRefused,
    check_spend_allowed,
    spend_snapshot,
)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _spend(db_session, amount, *, when=None, status=CostStatus.ESTIMATED):
    db_session.add(
        ProviderCall(
            provider="openai",
            model="gpt-5.5",
            capability="ocr",
            estimated_cost_usd=amount,
            cost_status=str(status),
            cost_status_reason=None if status is CostStatus.ESTIMATED else "unpriced",
            record_source=RECORD_SOURCE_PER_CALL,
            created_at=when or datetime.now(),
        )
    )
    db_session.commit()


def test_no_cap_configured_never_blocks(db_session):
    _spend(db_session, 999.0)
    snapshot = check_spend_allowed(db_session, cap_usd=None)
    assert snapshot.is_over_cap is False
    assert snapshot.remaining_usd is None


def test_under_cap_proceeds(db_session):
    _spend(db_session, 1.0)
    snapshot = check_spend_allowed(db_session, cap_usd=5.0)
    assert snapshot.spent_usd == pytest.approx(1.0)
    assert snapshot.remaining_usd == pytest.approx(4.0)


def test_at_or_over_cap_raises(db_session):
    _spend(db_session, 5.0)
    with pytest.raises(SpendLimitExceeded) as exc:
        check_spend_allowed(db_session, cap_usd=5.0)
    assert exc.value.snapshot.spent_usd == pytest.approx(5.0)


def test_429_detail_carries_everything_the_caller_needs(db_session):
    _spend(db_session, 10.0)
    with pytest.raises(SpendLimitExceeded) as exc:
        check_spend_allowed(db_session, cap_usd=5.0, estimated_unit_cost_usd=0.25)

    detail = exc.value.to_detail()
    assert detail["cap_usd"] == 5.0
    assert detail["spent_today_usd"] == pytest.approx(10.0)
    assert detail["estimated_unit_cost_usd"] == 0.25
    assert detail["resets_at"]
    assert "local calendar day" in detail["resets_at_note"]


def test_only_todays_local_spend_counts(db_session):
    """Yesterday's spend must not consume today's budget."""
    yesterday = datetime.now() - timedelta(days=1)
    _spend(db_session, 100.0, when=yesterday)
    _spend(db_session, 1.0)

    snapshot = spend_snapshot(db_session, cap_usd=5.0)
    assert snapshot.spent_usd == pytest.approx(1.0)
    assert snapshot.is_over_cap is False


def test_untrusted_costs_are_reported_not_silently_counted_as_zero(db_session):
    """
    A cap compared against a total that silently swallowed unknown costs
    would let real spend run past it invisibly.
    """
    _spend(db_session, 1.0)
    _spend(db_session, None, status=CostStatus.UNKNOWN)

    snapshot = spend_snapshot(db_session, cap_usd=5.0)
    assert snapshot.spent_usd == pytest.approx(1.0)
    assert snapshot.calls_with_untrusted_cost == 1

    with pytest.raises(SpendLimitExceeded) as exc:
        check_spend_allowed(db_session, cap_usd=0.5)
    assert "not included" in exc.value.to_detail()["note"].lower()


def test_read_only_endpoints_are_not_guarded(client, db_session):
    """Cost/reporting endpoints must never be blocked - they spend nothing."""
    _spend(db_session, 999.0)
    assert client.get("/api/costs/daily").status_code == 200
    assert client.get("/api/slideshows").status_code == 200


def test_paid_endpoint_returns_429_when_over_cap(client, db_session, slideshow_with_slide, monkeypatch):
    """
    End-to-end: the guard must be real code on the endpoint, not merely
    importable. (An earlier attempt inserted it inside a docstring, where
    it was inert and every test still passed - hence this test.)
    """
    monkeypatch.setattr("app.services.spend_limit.load_daily_cap_usd", lambda *a, **k: 1.0)
    _spend(db_session, 5.0)

    response = client.post(f"/api/slideshows/{slideshow_with_slide.id}/analyze")

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["error"] == "daily_spend_cap_reached"
    assert detail["cap_usd"] == 1.0
    assert detail["spent_today_usd"] == pytest.approx(5.0)
    assert detail["resets_at"]


def test_paid_endpoint_proceeds_when_under_cap_and_everything_is_priceable(
    client, db_session, slideshow_with_slide, monkeypatch
):
    monkeypatch.setattr("app.services.spend_limit.load_daily_cap_usd", lambda *a, **k: 100.0)
    # Every planned model priceable - the ordinary case.
    monkeypatch.setattr("app.services.spend_limit.has_usable_rate", lambda *a, **k: True)
    _spend(db_session, 1.0)

    response = client.post(f"/api/slideshows/{slideshow_with_slide.id}/analyze")

    assert response.status_code != 429


def test_enabling_the_cap_today_refuses_analysis_because_a_model_is_unpriced(
    client, db_session, slideshow_with_slide, monkeypatch
):
    """
    Follow-up item 1, end to end, against the REAL pricing config.

    This is the honest current state: gemini-pro-latest and the primary
    image model have no confirmed rate, so with a cap enabled the
    pipeline fails closed rather than letting unpriceable spend through.
    That is exactly why the cap ships disabled by default.
    """
    monkeypatch.setattr("app.services.spend_limit.load_daily_cap_usd", lambda *a, **k: 100.0)
    monkeypatch.setattr("app.services.spend_limit.load_unknown_cost_ceilings", lambda *a, **k: {})

    response = client.post(f"/api/slideshows/{slideshow_with_slide.id}/analyze")

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["error"] == "unpriced_work_refused"
    assert detail["unpriceable_calls"], "must name which models could not be priced"
    assert "how_to_resolve" in detail


# --- Follow-up item 1: the four policy branches, explicitly ----------

_UNPRICED = PlannedCall("nano_banana", "gemini-3.1-flash-image-preview", "image_generation", "image")
_PRICED = PlannedCall("openai", "gpt-5.5", "ocr", "token")


def test_cap_disabled_allows_unpriceable_work(db_session, monkeypatch):
    """Nothing is being enforced, so refusing would be pure friction."""
    monkeypatch.setattr("app.services.spend_limit.has_usable_rate", lambda *a, **k: False)

    snapshot = check_spend_allowed(db_session, planned=[_UNPRICED], cap_usd=None)

    assert snapshot.cap_usd is None


def test_cap_enabled_refuses_unpriceable_work_with_no_ceiling(db_session, monkeypatch):
    """The headline case: unknown must not behave like zero."""
    monkeypatch.setattr("app.services.spend_limit.has_usable_rate", lambda *a, **k: False)

    with pytest.raises(UnpricedWorkRefused) as exc:
        check_spend_allowed(db_session, planned=[_UNPRICED], cap_usd=10.0, ceilings={})

    detail = exc.value.to_detail()
    assert detail["error"] == "unpriced_work_refused"
    assert detail["unpriceable_calls"][0]["provider"] == "nano_banana"
    assert "could not be counted against the cap" in detail["reason"]


def test_cap_enabled_allows_unpriceable_work_when_a_ceiling_is_configured(db_session, monkeypatch):
    monkeypatch.setattr("app.services.spend_limit.has_usable_rate", lambda *a, **k: False)

    snapshot = check_spend_allowed(
        db_session,
        planned=[_UNPRICED],
        cap_usd=10.0,
        ceilings={"nano_banana": {"image_generation": 0.10}},
    )

    assert snapshot.cap_usd == 10.0


def test_a_configured_ceiling_still_consumes_budget(db_session, monkeypatch):
    """
    An unpriceable-but-ceilinged call must not be free in all but name -
    the reservation has to count against the cap.
    """
    monkeypatch.setattr("app.services.spend_limit.has_usable_rate", lambda *a, **k: False)
    _spend(db_session, 9.95)

    with pytest.raises(SpendLimitExceeded):
        check_spend_allowed(
            db_session,
            planned=[_UNPRICED],
            cap_usd=10.0,
            ceilings={"nano_banana": {"image_generation": 0.10}},
        )


def test_priceable_work_is_unaffected_by_the_policy(db_session, monkeypatch):
    monkeypatch.setattr("app.services.spend_limit.has_usable_rate", lambda *a, **k: True)
    _spend(db_session, 1.0)

    snapshot = check_spend_allowed(db_session, planned=[_PRICED], cap_usd=10.0, ceilings={})

    assert snapshot.remaining_usd == pytest.approx(9.0)
