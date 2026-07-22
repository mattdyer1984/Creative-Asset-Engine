"""
AnalysisRun-start helper for the new Slideshow/Slide pipeline (Phase 2.4
of the Slideshow/Slide migration).

Mirrors app.stages.execution.start_analysis_run exactly, except it keys
the new AnalysisRun on slide_id/slideshow_id instead of creative_id -
the old helper is left untouched (not generalized to accept either)
since the old, still-live pipeline depends on its exact creative_id-only
signature and this migration's whole strategy is to never modify that
pipeline until Phase 2.7.

mark_failed/mark_succeeded are NOT duplicated here - both are already
entity-agnostic (they only need the AnalysisRun row itself, not which
entity it's keyed on), so every new stage imports them directly from
app.stages.execution unchanged.
"""

from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun


def start_analysis_run(
    db: Session,
    *,
    analysis_type: str,
    provider: str,
    model_name: str,
    durable: bool,
    slide_id: str | None = None,
    slideshow_id: str | None = None,
) -> AnalysisRun:
    analysis_run = AnalysisRun(
        slide_id=slide_id,
        slideshow_id=slideshow_id,
        analysis_type=analysis_type,
        provider=provider,
        model_name=model_name,
    )
    db.add(analysis_run)
    if durable:
        db.commit()
        db.refresh(analysis_run)
    else:
        db.flush()
    return analysis_run
