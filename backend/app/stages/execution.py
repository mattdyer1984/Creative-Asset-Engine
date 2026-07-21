"""
Shared AnalysisRun lifecycle bookkeeping (plan §6.1/§13's Stage contract).

Every Stage.run() creates an AnalysisRun, does its own provider call and
artifact writes, and finishes by recording STATUS_SUCCEEDED or
STATUS_FAILED - previously ~10 near-identical lines copy-pasted into all
six stages. Factored out here as three small functions rather than one
do-everything wrapper, specifically so each stage's own try/except -
which varies stage to stage in exactly what it covers - is left
untouched. This refactor deduplicates only the surrounding bookkeeping;
it changes no stage's behavior, exception boundaries, or commit points.

Two "pending" durability styles exist across the six stages today,
preserved here rather than silently unified (deliberately: unifying them
is a real behavior change - crash-durability of the "an attempt was
made" record - not a refactor, and belongs in its own reviewed change,
not this one):

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
    creative_id: str,
    analysis_type: str,
    provider: str,
    model_name: str,
    durable: bool,
) -> AnalysisRun:
    analysis_run = AnalysisRun(
        creative_id=creative_id,
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
