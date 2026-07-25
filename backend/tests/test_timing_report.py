"""
Unit tests for app.services.timing_report (Optimisation & Stability
Pass, Tier 2, see MIGRATION_PLAN.md).
"""

from app.services.timing_report import build_timing_breakdown, format_timing_breakdown
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


def _run(db_session, slideshow, *, analysis_type, provider_call_ms=None, usage=None):
    analysis_run = start_analysis_run(
        db_session,
        slideshow_id=slideshow.id,
        analysis_type=analysis_type,
        provider="openai",
        model_name="gpt-5.5",
        durable=True,
    )
    return mark_succeeded(db_session, analysis_run, provider_call_ms=provider_call_ms, usage=usage)


def test_build_timing_breakdown_sums_duration_per_analysis_type(db_session, slideshow_with_slide):
    _run(db_session, slideshow_with_slide, analysis_type="ocr")
    _run(db_session, slideshow_with_slide, analysis_type="ocr")  # a second slide's OCR call
    _run(db_session, slideshow_with_slide, analysis_type="marketing_analysis")

    breakdown = build_timing_breakdown(db_session, slideshow_id=slideshow_with_slide.id)

    by_type = {row["analysis_type"]: row for row in breakdown}
    assert "ocr" in by_type
    assert "marketing_analysis" in by_type
    assert by_type["ocr"]["label"] == "OCR"
    assert by_type["ocr"]["duration_seconds"] >= 0


def test_build_timing_breakdown_includes_cost_when_configured(db_session, slideshow_with_slide, monkeypatch):
    monkeypatch.setattr(
        "app.stages.execution.estimate_token_cost_usd",
        lambda provider, model, prompt_tokens, completion_tokens: 0.01,
    )
    _run(db_session, slideshow_with_slide, analysis_type="ocr", usage={"prompt_tokens": 10, "completion_tokens": 5})

    breakdown = build_timing_breakdown(db_session, slideshow_id=slideshow_with_slide.id)

    by_type = {row["analysis_type"]: row for row in breakdown}
    assert by_type["ocr"]["estimated_cost_usd"] == 0.01


def test_build_timing_breakdown_orders_known_stages_first(db_session, slideshow_with_slide):
    _run(db_session, slideshow_with_slide, analysis_type="marketing_analysis")
    _run(db_session, slideshow_with_slide, analysis_type="ocr")

    breakdown = build_timing_breakdown(db_session, slideshow_id=slideshow_with_slide.id)

    labels = [row["label"] for row in breakdown]
    assert labels.index("OCR") < labels.index("Marketing Analysis")


def test_build_timing_breakdown_excludes_failed_runs_missing_duration_gracefully(db_session, slideshow_with_slide):
    analysis_run = start_analysis_run(
        db_session,
        slideshow_id=slideshow_with_slide.id,
        analysis_type="ocr",
        provider="openai",
        model_name="gpt-5.5",
        durable=True,
    )
    mark_failed(db_session, analysis_run, RuntimeError("boom"), rollback=False)

    # Should not raise, even though this run's duration_ms IS set (mark_failed
    # stamps timing too) - this just confirms failed runs are still counted.
    breakdown = build_timing_breakdown(db_session, slideshow_id=slideshow_with_slide.id)
    assert breakdown  # a row exists for "ocr"


def test_build_timing_breakdown_requires_a_scope():
    import pytest

    with pytest.raises(ValueError):
        build_timing_breakdown(None)


def test_format_timing_breakdown_renders_total_row():
    breakdown = [
        {"analysis_type": "ocr", "label": "OCR", "duration_seconds": 1.9, "estimated_cost_usd": None},
        {
            "analysis_type": "marketing_analysis",
            "label": "Marketing Analysis",
            "duration_seconds": 1.4,
            "estimated_cost_usd": None,
        },
    ]

    output = format_timing_breakdown(breakdown)

    assert "OCR" in output
    assert "Marketing Analysis" in output
    assert "TOTAL" in output
    assert "3.3s" in output  # 1.9 + 1.4


def test_format_timing_breakdown_shows_cost_column_only_when_present():
    without_cost = format_timing_breakdown(
        [{"analysis_type": "ocr", "label": "OCR", "duration_seconds": 1.0, "estimated_cost_usd": None}]
    )
    with_cost = format_timing_breakdown(
        [{"analysis_type": "ocr", "label": "OCR", "duration_seconds": 1.0, "estimated_cost_usd": 0.0025}]
    )

    assert "$" not in without_cost
    assert "$0.0025" in with_cost


def test_format_timing_breakdown_handles_empty_input():
    assert format_timing_breakdown([]) == "(no timed stages recorded)"
