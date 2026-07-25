"""
Unit tests for app.stages.execution's mark_succeeded/mark_failed timing
and cost stamping (Optimisation & Stability Pass, Tier 2, see
MIGRATION_PLAN.md) - the one shared place every Stage's AnalysisRun gets
finished_at/duration_ms/provider_call_ms/prompt_tokens/completion_tokens/
estimated_cost_usd "for free."
"""

from app.models.analysis_run import ANALYSIS_TYPE_OCR, STATUS_FAILED, STATUS_SUCCEEDED
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


def _start_run(db_session, *, durable=True):
    return start_analysis_run(
        db_session,
        analysis_type=ANALYSIS_TYPE_OCR,
        provider="openai",
        model_name="gpt-5.5",
        durable=durable,
    )


def test_mark_succeeded_stamps_finished_at_and_duration(db_session):
    analysis_run = _start_run(db_session)

    result = mark_succeeded(db_session, analysis_run)

    assert result.succeeded is True
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.finished_at is not None
    assert analysis_run.duration_ms is not None
    assert analysis_run.duration_ms >= 0


def test_mark_succeeded_stamps_provider_call_ms(db_session):
    analysis_run = _start_run(db_session)

    mark_succeeded(db_session, analysis_run, provider_call_ms=123.4)

    assert analysis_run.provider_call_ms == 123.4


def test_mark_succeeded_computes_cost_when_pricing_configured(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.stages.execution.estimate_token_cost_usd",
        lambda provider, model, prompt_tokens, completion_tokens: 0.0042,
    )

    analysis_run = _start_run(db_session)
    mark_succeeded(db_session, analysis_run, usage={"prompt_tokens": 100, "completion_tokens": 50})

    assert analysis_run.prompt_tokens == 100
    assert analysis_run.completion_tokens == 50
    assert analysis_run.estimated_cost_usd == 0.0042


def test_mark_succeeded_cost_is_none_without_usage(db_session):
    analysis_run = _start_run(db_session)

    mark_succeeded(db_session, analysis_run)

    assert analysis_run.prompt_tokens is None
    assert analysis_run.completion_tokens is None
    assert analysis_run.estimated_cost_usd is None


def test_mark_failed_also_stamps_timing(db_session):
    analysis_run = _start_run(db_session)

    result = mark_failed(db_session, analysis_run, RuntimeError("boom"), rollback=False)

    assert result.succeeded is False
    assert analysis_run.status == STATUS_FAILED
    assert analysis_run.finished_at is not None
    assert analysis_run.duration_ms is not None
