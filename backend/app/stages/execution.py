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

Two "pending" durability styles exist across the eight
SLIDESHOW_STAGE_PIPELINE stages (preserved, not unified - deliberately:
unifying them is a real behavior change, crash-durability of the "an
attempt was made" record, not a refactor):

  - durable=True (product_isolation, creative_fingerprint,
    scene_intelligence, marketing_analysis, narrative_structure,
    creative_specification): the pending AnalysisRun is committed
    BEFORE the stage's own risky work runs, so a process crash mid-call
    still leaves a durable record that the attempt happened. A failure
    inside the stage's try block rolls back whatever it wrote before
    recording the failure.
  - durable=False (ocr, product_lock_profile): the pending AnalysisRun
    is only flushed (id assigned, not yet committed) before the stage's
    own risky work runs; these two stages defer all their own DB writes
    until after the fallible call succeeds, so there's nothing to roll
    back on failure.

image_generation_stage.py and both of image_validation_stage.py's entry
points (outside SLIDESHOW_STAGE_PIPELINE - see their own module
docstrings for why) also use durable=True, same reasoning as the
pipeline stages above: a paid provider call in flight should always
leave a durable record, crash or not.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models._shared import utcnow
from app.models.analysis_run import STATUS_FAILED, STATUS_SUCCEEDED, AnalysisRun
from app.services.cost_estimation import estimate_token_cost_usd
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


def _as_naive_utc(dt: datetime) -> datetime:
    """
    analysis_run.created_at is written as a tz-aware datetime (utcnow())
    but the column has no timezone=True - SQLite drops the tz on
    storage, so a value re-read after a commit/refresh (durable=True's
    start_analysis_run does both) comes back naive while a value that
    never left memory (durable=False, flush-only) stays tz-aware -
    "can't subtract offset-naive and offset-aware datetimes" otherwise.
    Both are UTC regardless of which label they carry, so stripping
    tzinfo on both sides before subtracting is correct, not a hack.
    """
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


# AnalysisRun.analysis_type is a PIPELINE-STAGE axis; capability is the
# BILLING axis (WP-2). They are not the same thing - several stages
# share one capability. Anything unrecognised becomes "unknown" rather
# than being forced into a plausible-looking bucket.
_CAPABILITY_BY_ANALYSIS_TYPE = {
    "ocr": "ocr",
    "product_isolation": "product_isolation",
    "product_lock_profile": "vision_analysis",
    "creative_fingerprint": "vision_analysis",
    "scene_intelligence": "vision_analysis",
    "image_validation": "vision_analysis",
    "marketing_analysis": "text_generation",
    "narrative_structure": "text_generation",
    "creative_specification": "prompt_generation",
    "recreation_prompt": "prompt_generation",
    "generated_image": "image_generation",
}


def _stamp_timing_and_cost(
    analysis_run: AnalysisRun,
    *,
    provider_call_ms: float | None,
    usage: dict | None,
) -> None:
    """
    Optimisation & Stability Pass, Tier 2 (see MIGRATION_PLAN.md) - the
    one place duration/cost get computed, so every Stage gets this "for
    free" just by continuing to call mark_succeeded/mark_failed as it
    already did; no Stage needs its own bookkeeping.

    finished_at/duration_ms are wall-clock (analysis_run.created_at was
    stamped by start_analysis_run) - an approximation appropriate to the
    "where practical" ask, not a precise trace. provider_call_ms is
    optional (only stages that were updated to time their own provider
    call pass it); usage is the caller's usage_sink dict (or None), read
    here rather than duplicating the pricing lookup in every Stage.
    """
    finished_at = utcnow()
    analysis_run.finished_at = finished_at
    analysis_run.duration_ms = (
        _as_naive_utc(finished_at) - _as_naive_utc(analysis_run.created_at)
    ).total_seconds() * 1000
    analysis_run.provider_call_ms = provider_call_ms

    if usage:
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        analysis_run.prompt_tokens = prompt_tokens
        analysis_run.completion_tokens = completion_tokens
        analysis_run.estimated_cost_usd = estimate_token_cost_usd(
            analysis_run.provider, analysis_run.model_name, prompt_tokens, completion_tokens
        )


def mark_failed(
    db: Session,
    analysis_run: AnalysisRun,
    exc: Exception,
    *,
    rollback: bool,
    provider_call_ms: float | None = None,
    usage: dict | None = None,
) -> StageResult:
    if rollback:
        db.rollback()
    analysis_run.status = STATUS_FAILED
    analysis_run.error = str(exc)
    _stamp_timing_and_cost(analysis_run, provider_call_ms=provider_call_ms, usage=usage)
    db.commit()
    return StageResult(succeeded=False, error=str(exc))


def mark_succeeded(
    db: Session,
    analysis_run: AnalysisRun,
    *,
    provider_call_ms: float | None = None,
    usage: dict | None = None,
    emit_provider_call: bool = True,
    capability: str | None = None,
) -> StageResult:
    """
    Phase 1 remediation (WP-2): also emits the ProviderCall row that
    cost reporting now reads from.

    Emitting here rather than in each of the eight pipeline stages is
    deliberate - they all already funnel through this one function, so
    a new stage gets billing visibility by default instead of having to
    remember to add it. Cost reporting reads ProviderCall exclusively,
    so a stage that silently skipped this would vanish from spend
    entirely.

    `emit_provider_call=False` is for the call sites that record their
    own rows at finer granularity than one-per-stage - image validation
    makes two provider calls under a single AnalysisRun, and generation
    records one row per candidate. Those must opt out or they would be
    counted twice.

    Only emits when there is real usage to attribute: a stage that
    passes no usage_sink has nothing billable to record here (image
    generation's own cost is recorded at its call site, per-image).
    """
    analysis_run.status = STATUS_SUCCEEDED
    _stamp_timing_and_cost(analysis_run, provider_call_ms=provider_call_ms, usage=usage)

    if emit_provider_call and usage:
        # Imported lazily: app.services.provider_call_log imports pricing
        # helpers, and a module-level import here would create a cycle
        # with the stage modules that import this one.
        from app.services.provider_call_log import record_provider_call

        record_provider_call(
            db,
            provider=analysis_run.provider,
            model=analysis_run.model_name,
            capability=capability or _CAPABILITY_BY_ANALYSIS_TYPE.get(
                analysis_run.analysis_type, "unknown"
            ),
            usage=usage,
            provider_latency_ms=provider_call_ms,
            analysis_run_id=analysis_run.id,
            slide_id=analysis_run.slide_id,
            slideshow_id=analysis_run.slideshow_id,
        )

    db.commit()
    return StageResult(succeeded=True)
