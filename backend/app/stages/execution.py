"""
Shared AnalysisRun lifecycle bookkeeping - every Stage.run() creates an
AnalysisRun, does its own provider call and artifact writes, and
finishes by recording STATUS_SUCCEEDED or STATUS_FAILED. Factored out as
three small functions rather than one do-everything wrapper, so each
stage's own try/except - which varies stage to stage in exactly what it
covers - stays in the stage itself.

start_analysis_run keys the new AnalysisRun on whichever of slide_id/
slideshow_id the calling stage passes (never both meaningfully at once
in practice: slide-scoped stages pass slide_id, slideshow-scoped stages
pass slideshow_id - see app.slideshow_stages.base's docstring). Until
the Phase 2 engineering review this lived in two near-identical copies
(this file had a creative_id-keyed version for the old, now-deleted
pipeline; app.slideshow_stages.execution had this slide_id/slideshow_id
version) - merged into this one during that review once the old version
had zero remaining callers.

Two "pending" durability styles exist across the six stages (preserved,
not unified - deliberately: unifying them is a real behavior change,
crash-durability of the "an attempt was made" record, not a refactor):

  - durable=True (isolation, fingerprint, marketing_analysis,
    recreation_prompt): the pending AnalysisRun is committed BEFORE the
    stage's own risky work runs, so a process crash mid-call still
    leaves a durable record that the attempt happened. A failure inside
    the stage's try block rolls back whatever it wrote before recording
    the failure.
  - durable=False (ocr, product_lock_profile): the pending AnalysisRun
    is only flushed (id assigned, not yet committed) before the stage's
    own risky work runs; these two stages defer all their own DB writes
    until after the fallible call succeeds, so there's nothing to roll
    back on failure.
"""

from sqlalchemy.orm import Session

from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.stages.base import StageResult


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


def mark_failed(
    db: Session, analysis_run: AnalysisRun, exc: Exception, *, rollback: bool
) -> StageResult:
    if rollback:
        db.rollback()
    analysis_run.status = STATUS_FAILED
    analysis_run.error = str(exc)
    db.commit()
    return StageResult(succeeded=False, error=str(exc))


def mark_succeeded(db: Session, analysis_run: AnalysisRun) -> StageResult:
    analysis_run.status = STATUS_SUCCEEDED
    db.commit()
    return StageResult(succeeded=True)
