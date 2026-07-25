"""
ProviderCall instrumentation tests (Phase 1 remediation, WP-2).

The properties that matter:
  * one row per PROVIDER CALL, not per stage - a stage making two calls
    must produce two rows (the double-counting regression);
  * calls that previously produced no record at all now produce one;
  * costs come from ONE path and never silently mix untrustworthy
    figures into a total;
  * reconstructed history stays distinguishable from genuine records.
"""

import pytest
from sqlalchemy import select

from app.models.provider_call import (
    RECORD_SOURCE_LEGACY_AGGREGATE,
    RECORD_SOURCE_PER_CALL,
    ProviderCall,
)
from app.services.cost_estimation import CostStatus
from app.services.provider_call_log import record_provider_call

PRICED = {
    "pricing": {
        "openai": {"gpt-5.5": {"per_1k_prompt_tokens": 0.005, "per_1k_completion_tokens": 0.030}}
    }
}


def test_records_a_call_with_usage_and_cost(db_session, monkeypatch):
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)

    call = record_provider_call(
        db_session,
        provider="openai",
        model="gpt-5.5",
        capability="vision_analysis",
        usage={"prompt_tokens": 1000, "completion_tokens": 1000},
        provider_latency_ms=1234.5,
    )

    assert call is not None
    assert call.record_source == RECORD_SOURCE_PER_CALL
    assert call.cost_status == str(CostStatus.ESTIMATED)
    assert call.estimated_cost_usd == pytest.approx(0.035)
    assert call.provider_latency_ms == pytest.approx(1234.5)


def test_a_missing_rate_is_recorded_as_unknown_with_a_reason(db_session, monkeypatch):
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)

    call = record_provider_call(
        db_session,
        provider="nano_banana",
        model="some-unpriced-model",
        capability="image_generation",
        image_count=1,
    )

    assert call.cost_status == str(CostStatus.UNKNOWN)
    assert call.estimated_cost_usd is None, "unknown must be None, never 0.0"
    assert call.cost_status_reason, "unknown cost must always say why"


def test_partial_cost_records_which_component_was_missing(db_session, monkeypatch):
    """An unqualified 'partial' is useless when auditing later."""
    prompt_only = {"pricing": {"openai": {"m": {"per_1k_prompt_tokens": 0.005}}}}
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: prompt_only)

    call = record_provider_call(
        db_session,
        provider="openai",
        model="m",
        capability="text_generation",
        usage={"prompt_tokens": 1000, "completion_tokens": 1000},
    )

    assert call.cost_status == str(CostStatus.PARTIAL)
    assert "missing completion rate" in call.cost_status_reason


def test_telemetry_failure_never_raises(db_session, monkeypatch):
    """A bookkeeping bug must never destroy a result the user already paid for."""
    def boom(*a, **k):
        raise RuntimeError("pricing blew up")

    monkeypatch.setattr("app.services.provider_call_log.estimate_token_cost", boom)

    result = record_provider_call(
        db_session, provider="openai", model="gpt-5.5", capability="ocr", usage={}
    )
    assert result is None  # recorded nothing, but did not raise


def test_two_calls_under_one_analysis_run_produce_two_rows(db_session, monkeypatch):
    """
    The double-counting regression. image_validation_stage opens ONE
    AnalysisRun and makes TWO provider calls under it; folding those into
    the run would either double-count or lose per-call attribution.
    """
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)

    from app.models.analysis_run import AnalysisRun

    run = AnalysisRun(
        analysis_type="image_validation", provider="openai", model_name="gpt-5.5", status="succeeded"
    )
    db_session.add(run)
    db_session.flush()

    for _ in range(2):
        record_provider_call(
            db_session,
            provider="openai",
            model="gpt-5.5",
            capability="vision_analysis",
            usage={"prompt_tokens": 100, "completion_tokens": 100},
            analysis_run_id=run.id,
        )
    db_session.flush()

    rows = list(
        db_session.scalars(select(ProviderCall).where(ProviderCall.analysis_run_id == run.id))
    )
    assert len(rows) == 2, "one AnalysisRun must be able to hold two distinct ProviderCalls"


def test_legacy_rows_are_distinguishable_from_genuine_ones(db_session, monkeypatch):
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)

    record_provider_call(
        db_session, provider="openai", model="gpt-5.5", capability="ocr",
        usage={"prompt_tokens": 10, "completion_tokens": 10},
    )
    db_session.add(
        ProviderCall(
            provider="openai", model="gpt-5.5", capability="ocr",
            cost_status=str(CostStatus.UNKNOWN),
            cost_status_reason="legacy aggregate",
            record_source=RECORD_SOURCE_LEGACY_AGGREGATE,
        )
    )
    db_session.flush()

    genuine = list(
        db_session.scalars(
            select(ProviderCall).where(ProviderCall.record_source == RECORD_SOURCE_PER_CALL)
        )
    )
    legacy = list(
        db_session.scalars(
            select(ProviderCall).where(
                ProviderCall.record_source == RECORD_SOURCE_LEGACY_AGGREGATE
            )
        )
    )
    assert len(genuine) == 1
    assert len(legacy) == 1


def test_daily_costs_exclude_untrustworthy_figures_from_the_total(db_session, monkeypatch):
    """
    A total must never quietly under-report. partial/unknown rows are
    counted and surfaced, never summed into money.
    """
    from app.routers.costs import get_daily_costs

    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)

    record_provider_call(
        db_session, provider="openai", model="gpt-5.5", capability="ocr",
        usage={"prompt_tokens": 1000, "completion_tokens": 1000},
    )
    db_session.add(
        ProviderCall(
            provider="openai", model="mystery", capability="ocr",
            estimated_cost_usd=None, cost_status=str(CostStatus.UNKNOWN),
            cost_status_reason="no rate", record_source=RECORD_SOURCE_PER_CALL,
        )
    )
    db_session.add(
        ProviderCall(
            provider="openai", model="half", capability="ocr",
            estimated_cost_usd=0.005, cost_status=str(CostStatus.PARTIAL),
            cost_status_reason="missing completion rate", record_source=RECORD_SOURCE_PER_CALL,
        )
    )
    db_session.commit()

    rows = get_daily_costs(db=db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.call_count == 3
    assert row.calls_with_unknown_cost == 1
    assert row.calls_with_partial_cost == 1
    # Only the fully-costed call contributes money.
    assert row.known_cost_subtotal_usd == pytest.approx(0.035)


def test_breakdown_supports_every_required_axis(db_session, monkeypatch):
    from app.routers.costs import get_cost_breakdown

    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)
    record_provider_call(
        db_session, provider="openai", model="gpt-5.5", capability="ocr",
        usage={"prompt_tokens": 1000, "completion_tokens": 1000},
    )
    db_session.commit()

    for axis in ("provider", "model", "capability", "slideshow", "slide"):
        rows = get_cost_breakdown(db=db_session, group_by=axis)
        assert isinstance(rows, list), f"axis {axis} must be queryable"

    by_capability = get_cost_breakdown(db=db_session, group_by="capability")
    assert by_capability[0].key == "ocr"
    assert by_capability[0].known_cost_subtotal_usd == pytest.approx(0.035)


def test_pipeline_stages_emit_provider_calls_via_mark_succeeded(db_session, monkeypatch):
    """
    Guards a regression that would have silently zeroed all analysis
    spend: cost reporting reads ProviderCall exclusively, so a pipeline
    stage that does not emit one vanishes from spend entirely. Emission
    lives in mark_succeeded precisely so a new stage gets it by default.
    """
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)

    from app.models.analysis_run import AnalysisRun
    from app.stages.execution import mark_succeeded

    run = AnalysisRun(
        analysis_type="ocr", provider="openai", model_name="gpt-5.5", status="pending"
    )
    db_session.add(run)
    db_session.flush()

    mark_succeeded(
        db_session,
        run,
        provider_call_ms=500.0,
        usage={"prompt_tokens": 1000, "completion_tokens": 1000},
    )

    rows = list(
        db_session.scalars(select(ProviderCall).where(ProviderCall.analysis_run_id == run.id))
    )
    assert len(rows) == 1
    assert rows[0].capability == "ocr", "analysis_type must map onto the billing axis"
    assert rows[0].estimated_cost_usd == pytest.approx(0.035)


def test_mark_succeeded_can_opt_out_to_avoid_double_counting(db_session, monkeypatch):
    """Sites recording their own finer-grained rows must be able to opt out."""
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: PRICED)

    from app.models.analysis_run import AnalysisRun
    from app.stages.execution import mark_succeeded

    run = AnalysisRun(
        analysis_type="image_validation", provider="openai", model_name="gpt-5.5", status="pending"
    )
    db_session.add(run)
    db_session.flush()

    mark_succeeded(
        db_session,
        run,
        usage={"prompt_tokens": 10, "completion_tokens": 10},
        emit_provider_call=False,
    )

    rows = list(
        db_session.scalars(select(ProviderCall).where(ProviderCall.analysis_run_id == run.id))
    )
    assert rows == []


def test_a_stage_with_no_usage_emits_nothing(db_session):
    """Nothing billable to attribute - must not create an empty phantom row."""
    from app.models.analysis_run import AnalysisRun
    from app.stages.execution import mark_succeeded

    run = AnalysisRun(
        analysis_type="ocr", provider="openai", model_name="gpt-5.5", status="pending"
    )
    db_session.add(run)
    db_session.flush()

    mark_succeeded(db_session, run, provider_call_ms=100.0)

    rows = list(
        db_session.scalars(select(ProviderCall).where(ProviderCall.analysis_run_id == run.id))
    )
    assert rows == []


# --- Follow-up to Checkpoint B, item 2: alias vs resolved model -------

ALIAS_PRICED = {
    "pricing": {
        "gemini": {
            "gemini-flash-latest": {
                "reported_model": "gemini-3.6-flash",
                "per_1k_prompt_tokens": 0.0015,
                "per_1k_completion_tokens": 0.0075,
            }
        }
    }
}


def test_records_both_requested_alias_and_resolved_model(db_session, monkeypatch):
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: ALIAS_PRICED)

    call = record_provider_call(
        db_session,
        provider="gemini",
        model="gemini-flash-latest",
        capability="ocr",
        usage={
            "prompt_tokens": 1000,
            "completion_tokens": 1000,
            "reported_model": "gemini-3.6-flash",
        },
    )

    assert call.model == "gemini-flash-latest", "the requested alias must be preserved"
    assert call.reported_model == "gemini-3.6-flash", "the resolved model must be recorded"
    assert call.cost_status == str(CostStatus.ESTIMATED)
    assert call.estimated_cost_usd == pytest.approx(0.0015 + 0.0075)


def test_alias_repointed_to_an_unpriced_model_becomes_unknown_not_stale(db_session, monkeypatch):
    """
    The whole point of item 2: if Google repoints gemini-flash-latest at
    a model we have never priced, cost must become explicitly unknown -
    NOT keep billing at the old alias rate, which would be confidently
    wrong and invisible.
    """
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: ALIAS_PRICED)

    call = record_provider_call(
        db_session,
        provider="gemini",
        model="gemini-flash-latest",
        capability="ocr",
        usage={
            "prompt_tokens": 1000,
            "completion_tokens": 1000,
            "reported_model": "gemini-4.0-flash",  # a repoint we never priced
        },
    )

    assert call.cost_status == str(CostStatus.UNKNOWN)
    assert call.estimated_cost_usd is None, "must not reuse the alias's stale rate"
    assert "gemini-4.0-flash" in call.cost_status_reason
    assert "stale" in call.cost_status_reason
    assert call.reported_model == "gemini-4.0-flash"


def test_resolved_model_priced_directly_is_preferred(db_session, monkeypatch):
    """When the resolved snapshot itself has a rate, use it."""
    pricing = {
        "pricing": {
            "openai": {
                "gpt-5.5": {"per_1k_prompt_tokens": 99.0, "per_1k_completion_tokens": 99.0},
                "gpt-5.5-2026-04-23": {
                    "per_1k_prompt_tokens": 0.005,
                    "per_1k_completion_tokens": 0.030,
                },
            }
        }
    }
    monkeypatch.setattr("app.services.cost_estimation.load_pricing", lambda *a, **k: pricing)

    call = record_provider_call(
        db_session,
        provider="openai",
        model="gpt-5.5",
        capability="ocr",
        usage={
            "prompt_tokens": 1000,
            "completion_tokens": 1000,
            "reported_model": "gpt-5.5-2026-04-23",
        },
    )

    # The snapshot's own rate, not the alias entry's.
    assert call.estimated_cost_usd == pytest.approx(0.035)


# --- Follow-up to Checkpoint B, items 4 & 5 -------------------------


def _row(db, **overrides):
    defaults = dict(
        provider="openai",
        model="gpt-5.5",
        capability="ocr",
        prompt_tokens=1000,
        completion_tokens=1000,
        provider_latency_ms=500.0,
        estimated_cost_usd=0.035,
        cost_status=str(CostStatus.ESTIMATED),
        record_source=RECORD_SOURCE_PER_CALL,
    )
    defaults.update(overrides)
    call = ProviderCall(**defaults)
    db.add(call)
    db.flush()
    return call


def test_legacy_rows_are_never_counted_as_provider_calls(db_session):
    """
    Item 4: a reconstructed row may stand for several real calls, and the
    latency stored on it is stage wall-clock, not provider time. It must
    contribute to money ONLY - never to call counts, latency or tokens,
    which are exactly the figures a per-call average is built from.
    """
    from app.routers.costs import get_cost_breakdown, get_daily_costs

    _row(db_session)
    _row(
        db_session,
        record_source=RECORD_SOURCE_LEGACY_AGGREGATE,
        provider_latency_ms=99_000.0,
        prompt_tokens=50_000,
        completion_tokens=50_000,
    )
    db_session.commit()

    daily = get_daily_costs(db=db_session)[0]
    assert daily.call_count == 1, "a reconstructed row is not a provider call"
    assert daily.legacy_aggregate_rows == 1, "but it must still be visible"

    row = get_cost_breakdown(db=db_session, group_by="capability")[0]
    assert row.call_count == 1
    assert row.legacy_aggregate_rows == 1
    assert row.total_provider_latency_ms == pytest.approx(500.0), (
        "the legacy row's 99s of stage wall-clock must not be reported as provider latency"
    )
    assert row.prompt_tokens == 1000, "legacy tokens are not per-call evidence"
    # Money is the one figure a reconstructed row can still support.
    assert row.known_cost_subtotal_usd == pytest.approx(0.07)


def test_incomplete_costs_are_named_as_such_not_as_a_total(db_session):
    """
    Item 5: when anything could not be priced, the report says so. The
    money field is a subtotal of what is KNOWN and is never presented as
    a total.
    """
    from app.routers.costs import get_daily_costs

    _row(db_session)
    _row(db_session, estimated_cost_usd=None, cost_status=str(CostStatus.UNKNOWN))
    db_session.commit()

    daily = get_daily_costs(db=db_session)[0]
    assert not hasattr(daily, "total_estimated_cost_usd"), "the misleading name is gone"
    assert daily.known_cost_subtotal_usd == pytest.approx(0.035)
    assert daily.calls_with_unknown_cost == 1
    assert daily.cost_completeness == "incomplete"


def test_fully_priced_days_read_as_complete(db_session):
    """The counterpart: do not cry "incomplete" when nothing is missing."""
    from app.routers.costs import get_daily_costs

    _row(db_session)
    db_session.commit()
    assert get_daily_costs(db=db_session)[0].cost_completeness == "complete"
