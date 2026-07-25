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

logger = logging.getLogger(__name__)


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

        outcome: tuple[str | None, StageResult]
        for stage in self.stages:
            try:
                result = stage.run(db, slideshow)
            except Exception as exc:
                # A stage is only ever supposed to raise for a genuine bug
                # (see SlideshowAnalysisStage.run's own docstring) - but if
                # one does, the Slideshow was already committed at
                # STATUS_ANALYZING above and must not be left there
                # forever. Same terminal-state contract as an ordinary
                # StageResult(succeeded=False) below, just reached via an
                # unexpected exception instead of an expected one.
                db.rollback()
                slideshow.status = STATUS_FAILED
                slideshow.last_failed_stage = stage.name
                slideshow.last_failed_stage_error = str(exc)
                db.commit()
                outcome = stage.name, StageResult(succeeded=False, error=str(exc))
                break

            if not result.succeeded:
                slideshow.status = STATUS_FAILED
                slideshow.last_failed_stage = stage.name
                slideshow.last_failed_stage_error = result.error
                db.commit()
                outcome = stage.name, result
                break
        else:
            slideshow.status = STATUS_READY
            slideshow.last_failed_stage = None
            slideshow.last_failed_stage_error = None
            db.commit()
            outcome = None, StageResult(succeeded=True)

        self._log_timing_breakdown(db, slideshow)
        return outcome

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
