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

from sqlalchemy.orm import Session

from app.models.slideshow import (
    STATUS_ANALYZING,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_READY,
    Slideshow,
)
from app.slideshow_stages.base import SlideshowAnalysisStage, StageResult
from app.slideshow_stages.pipeline import SLIDESHOW_STAGE_PIPELINE


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

        for stage in self.stages:
            result = stage.run(db, slideshow)
            if not result.succeeded:
                slideshow.status = STATUS_FAILED
                slideshow.last_failed_stage = stage.name
                slideshow.last_failed_stage_error = result.error
                db.commit()
                return stage.name, result

        slideshow.status = STATUS_READY
        slideshow.last_failed_stage = None
        slideshow.last_failed_stage_error = None
        db.commit()
        return None, StageResult(succeeded=True)

    def run_single_stage(
        self, db: Session, slideshow: Slideshow, stage_name: str
    ) -> StageResult:
        """Reruns exactly one stage without touching any other."""
        stage = next((s for s in self.stages if s.name == stage_name), None)
        if stage is None:
            raise ValueError(f"Unknown stage '{stage_name}'")

        slideshow.status = STATUS_ANALYZING
        db.commit()

        result = stage.run(db, slideshow)
        slideshow.status = STATUS_READY if result.succeeded else STATUS_FAILED
        slideshow.last_failed_stage = None if result.succeeded else stage.name
        slideshow.last_failed_stage_error = None if result.succeeded else result.error
        db.commit()

        return result


default_slideshow_orchestrator = SlideshowOrchestrator()
