"""
Spend forecasting and run-level controls (P3).

`spend_limit` answers "may this call proceed?". An operator needs a different
question answered before anything is spent: "what will this run cost, and do
I want to authorise it?"
"""

import pytest

from app.models.analysis_run import AnalysisRun
from app.models.provider_call import ProviderCall
from app.services.spend_forecast import (
    authorise_run,
    forecast_run,
    reconcile,
)


def _call(db, stage, cost, capability="vision_analysis"):
    run = AnalysisRun(analysis_type=stage, provider="p", model_name="m", status="succeeded")
    db.add(run)
    db.flush()
    call = ProviderCall(
        analysis_run_id=run.id, provider="p", model="m", capability=capability,
        estimated_cost_usd=cost,
        cost_status="estimated" if cost is not None else "unknown",
        record_source="per_call",
    )
    db.add(call)
    db.flush()
    return call


def test_a_stage_with_history_is_forecast_from_its_median(db_session):
    for cost in (0.01, 0.02, 0.03, 0.90):     # 0.90 is an outlier
        _call(db_session, "ocr", cost)
    stage = forecast_run(db_session, ["ocr"]).stages[0]
    assert stage.known_usd == pytest.approx(0.025)
    assert "median" in stage.basis


def test_the_median_resists_a_single_expensive_run(db_session):
    """
    A mean would let one retry storm quietly inflate every future forecast.
    """
    for cost in (0.01, 0.01, 0.01, 50.0):
        _call(db_session, "ocr", cost)
    assert forecast_run(db_session, ["ocr"]).stages[0].known_usd < 0.05


def test_too_little_history_is_reported_as_unpriced_not_guessed(db_session):
    _call(db_session, "ocr", 0.01)
    stage = forecast_run(db_session, ["ocr"]).stages[0]
    assert stage.known_usd is None
    assert "too few observations" in stage.basis


def test_a_deterministic_stage_forecasts_zero_with_certainty(db_session):
    """
    Forecasting it as unknown would put phantom uncertainty into every
    estimate - text_ownership genuinely costs nothing.
    """
    stage = forecast_run(db_session, ["text_ownership"]).stages[0]
    assert stage.known_usd == 0.0
    assert stage.unpriced_calls == 0
    assert stage.calls == 0


def test_an_incomplete_forecast_refuses_to_state_a_total(db_session):
    """
    The reporting rule this project has held throughout: adding NULLs as
    zero is how an incomplete figure gets presented as a complete one.
    """
    for cost in (0.01, 0.02, 0.03):
        _call(db_session, "ocr", cost)
    _call(db_session, "image_generation", None)
    forecast = forecast_run(db_session, ["ocr", "image_generation"])
    assert not forecast.is_complete
    assert "INCOMPLETE" in forecast.headline


def test_a_complete_forecast_states_a_total_plainly(db_session):
    for cost in (0.01, 0.02, 0.03):
        _call(db_session, "ocr", cost)
    forecast = forecast_run(db_session, ["ocr"])
    assert forecast.is_complete
    assert "INCOMPLETE" not in forecast.headline


def test_slides_multiply_the_forecast(db_session):
    for cost in (0.01, 0.01, 0.01):
        _call(db_session, "ocr", cost)
    one = forecast_run(db_session, ["ocr"], slides=1).known_subtotal_usd
    five = forecast_run(db_session, ["ocr"], slides=5).known_subtotal_usd
    assert five == pytest.approx(one * 5)


# --- authorisation --------------------------------------------------------


def _priced(db):
    for cost in (0.10, 0.10, 0.10):
        _call(db, "ocr", cost)


def test_a_run_within_limits_is_allowed(db_session):
    _priced(db_session)
    decision = authorise_run(db_session, ["ocr"], hard_stop_usd=10.0)
    assert decision.allowed


def test_the_hard_stop_refuses_before_anything_is_spent(db_session):
    """Absolute, unlike the soft daily cap: nothing starts that would cross it."""
    _priced(db_session)
    decision = authorise_run(db_session, ["ocr"], hard_stop_usd=0.01)
    assert not decision.allowed
    assert "hard stop" in decision.reason


def test_the_soft_cap_allows_the_run_but_says_so(db_session):
    """
    Soft means per-call enforcement stops it partway - the forecast is not
    accurate enough to be the sole guard.
    """
    _priced(db_session)
    decision = authorise_run(db_session, ["ocr"], daily_cap_usd=0.01)
    assert decision.allowed
    assert "soft daily cap" in decision.reason


def test_an_unpriceable_run_is_refused_by_default(db_session):
    """
    Unknown cost must never behave like zero. The most expensive part of
    this workflow is exactly the part currently unpriced.
    """
    _call(db_session, "image_generation", None)
    decision = authorise_run(db_session, ["image_generation"])
    assert not decision.allowed
    assert "cannot be priced" in decision.reason


def test_unpriced_work_can_be_authorised_deliberately(db_session):
    _call(db_session, "image_generation", None)
    decision = authorise_run(db_session, ["image_generation"], allow_unpriced=True)
    assert decision.allowed


def test_the_decision_renders_everything_an_operator_needs(db_session):
    _priced(db_session)
    text = authorise_run(
        db_session, ["ocr"], daily_cap_usd=1.0, hard_stop_usd=5.0
    ).render()
    for expected in ("spent today", "daily cap", "hard stop", "decision"):
        assert expected in text


# --- reconciliation -------------------------------------------------------


def test_reconciliation_reports_variance_against_the_forecast(db_session):
    """
    An estimate nobody checks drifts silently. This is what makes the
    forecast improvable rather than decorative.
    """
    _priced(db_session)
    forecast = forecast_run(db_session, ["ocr"])
    actual = _call(db_session, "ocr", 0.25)
    text = reconcile(db_session, forecast, [actual.id])
    assert "estimated known" in text and "actual known" in text
    assert "variance" in text


def test_reconciliation_flags_an_incomplete_comparison(db_session):
    _priced(db_session)
    forecast = forecast_run(db_session, ["ocr"])
    actual = _call(db_session, "ocr", None)
    assert "INCOMPLETE" in reconcile(db_session, forecast, [actual.id])
