"""
SlideshowOrchestrator — the parallel-pipeline equivalent of
app.orchestrator.AnalysisOrchestrator (Phase 2.4e of the Slideshow/Slide
migration).

Deliberately as thin as the original: iterate stages in order, stop and
mark the Slideshow failed on the first failure, mark ready if every
stage succeeds, move the Slideshow through queued -> analyzing at the
right moments. Contains no analysis logic of its own - identical
division of responsibility to the old orchestrator, just operating on
Slideshow directly instead of Creative + CreativeBlueprint.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.models.slideshow import (
    STATUS_ANALYZING,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_READY,
    Slideshow,
)
from app.services.timing_report import build_timing_breakdown, format_timing_breakdown
from app.slideshow_stages.base import SlideshowAnalysisStage, StageResult
from app.slideshow_stages.pipeline import SLIDESHOW_STAGE_PIPELINE
from app.slideshow_stages.scheduling import describe_waves, plan_waves

logger = logging.getLogger(__name__)

def _sequential_requested() -> bool:
    """
    O1. Concurrent stage execution is on by default; `CAE_SEQUENTIAL_STAGES=1`
    forces the old schedule. Read through Settings rather than os.environ so
    the config guard knows about it - it caught this flag being undeclared
    the first time, which is what that guard is for.
    """
    from app.config import settings

    return settings.sequential_stages


class SlideshowOrchestrator:
    def __init__(self, stages: list[SlideshowAnalysisStage] | None = None):
        self.stages = stages if stages is not None else SLIDESHOW_STAGE_PIPELINE

    def run_full_pipeline(
        self, db: Session, slideshow: Slideshow
    ) -> tuple[str | None, StageResult]:
        slideshow.status = STATUS_QUEUED
        db.commit()

        slideshow.status = STATUS_ANALYZING
        db.commit()

        waves = plan_waves(self.stages)
        sequential = _sequential_requested() or all(len(w) == 1 for w in waves)
        if not sequential:
            logger.info("Slideshow %s stage schedule: %s", slideshow.id, describe_waves(waves))

        outcome: tuple[str | None, StageResult]
        ordered = (
            [[stage] for stage in self.stages] if sequential else waves
        )
        failure = None
        for wave in ordered:
            failure = self._run_wave(db, slideshow, wave)
            if failure is not None:
                break

        if failure is not None:
            stage_name, result = failure
            slideshow.status = STATUS_FAILED
            slideshow.last_failed_stage = stage_name
            slideshow.last_failed_stage_error = result.error
            db.commit()
            outcome = stage_name, result
        else:
            slideshow.status = STATUS_READY
            slideshow.last_failed_stage = None
            slideshow.last_failed_stage_error = None
            db.commit()
            outcome = None, StageResult(succeeded=True)

        self._log_timing_breakdown(db, slideshow)
        return outcome

    def _run_wave(
        self, db: Session, slideshow: Slideshow, wave: list
    ) -> tuple[str, StageResult] | None:
        """
        Run one wave, returning the first failure in DECLARATION order.

        Concurrent execution cannot stop at the first failure the way the
        sequential loop did - the other stages are already in flight. So the
        wave runs to completion and the earliest-declared failure is
        reported, which keeps the reported failure stable regardless of
        which thread happened to finish first.
        """
        if len(wave) == 1:
            return self._run_one(db, slideshow, wave[0])

        # Each thread gets its own Session: SQLAlchemy Sessions are not
        # thread-safe, and sharing one would interleave flushes from
        # different stages into a single unit of work.
        from app.db import SessionLocal

        # Read the id HERE, on the calling thread. Touching any attribute of
        # an ORM object from a worker thread can trigger a lazy refresh
        # against the session that owns it, which is precisely the unsafe
        # access this isolation exists to prevent - and it fails as an
        # ObjectDeletedError far from the real cause.
        slideshow_id = slideshow.id

        def _isolated(stage):
            session = SessionLocal()
            try:
                own_slideshow = session.get(Slideshow, slideshow_id)
                if own_slideshow is None:
                    return stage.name, StageResult(
                        succeeded=False,
                        error=f"slideshow {slideshow_id} is not visible to this session",
                    )
                return self._run_one(session, own_slideshow, stage)
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=len(wave)) as executor:
            outcomes = list(executor.map(_isolated, wave))

        # The orchestrator's own session still holds the pre-wave state of
        # every row the wave just committed through other sessions.
        db.expire_all()

        for outcome in outcomes:
            if outcome is not None:
                return outcome
        return None

    def _run_one(
        self, db: Session, slideshow: Slideshow, stage
    ) -> tuple[str, StageResult] | None:
        try:
            result = stage.run(db, slideshow)
        except Exception as exc:
            # A stage is only ever supposed to raise for a genuine bug (see
            # SlideshowAnalysisStage.run's own docstring) - but if one does,
            # the Slideshow was already committed at STATUS_ANALYZING and
            # must not be left there forever.
            db.rollback()
            logger.exception("stage %s raised", stage.name)
            return stage.name, StageResult(succeeded=False, error=str(exc))

        return None if result.succeeded else (stage.name, result)

    def _log_timing_breakdown(self, db: Session, slideshow: Slideshow) -> None:
        """
        Optimisation & Stability Pass, Tier 1/2 (see MIGRATION_PLAN.md) -
        the timing/cost breakdown requested for the analysis pipeline.
        Logged unconditionally (success or failure) - whatever stages
        actually ran before a failure stopped the pipeline is still
        useful to see. Best-effort: a reporting failure must never mask
        the real pipeline outcome already computed above.
        """
        try:
            breakdown = build_timing_breakdown(db, slideshow_id=slideshow.id)
            logger.info(
                "Slideshow %s analysis timing:\n%s", slideshow.id, format_timing_breakdown(breakdown)
            )
        except Exception:
            logger.exception("Failed to build timing breakdown for slideshow %s", slideshow.id)

    def run_single_stage(
        self, db: Session, slideshow: Slideshow, stage_name: str
    ) -> StageResult:
        """Reruns exactly one stage without touching any other."""
        stage = next((s for s in self.stages if s.name == stage_name), None)
        if stage is None:
            raise ValueError(f"Unknown stage '{stage_name}'")

        slideshow.status = STATUS_ANALYZING
        db.commit()

        try:
            result = stage.run(db, slideshow)
        except Exception as exc:
            # Same reasoning as run_full_pipeline's try/except above - an
            # unexpected exception must still land the Slideshow on a
            # terminal status, not leave it stuck at STATUS_ANALYZING.
            db.rollback()
            result = StageResult(succeeded=False, error=str(exc))

        slideshow.status = STATUS_READY if result.succeeded else STATUS_FAILED
        slideshow.last_failed_stage = None if result.succeeded else stage.name
        slideshow.last_failed_stage_error = None if result.succeeded else result.error
        db.commit()

        return result


default_slideshow_orchestrator = SlideshowOrchestrator()
