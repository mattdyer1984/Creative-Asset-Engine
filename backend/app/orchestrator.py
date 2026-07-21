"""
AnalysisOrchestrator (plan §6.2).

Deliberately thin: iterate stages in order, stop and mark the Blueprint
failed on the first failure, mark ready if every stage succeeds, and move
the Blueprint through queued -> analyzing at the right moments. Contains
no analysis logic of its own - that all lives in the Stages.
"""

from sqlalchemy.orm import Session

from app.models.creative import Creative
from app.models.creative_blueprint import (
    STATUS_ANALYZING,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_READY,
)
from app.stages.base import AnalysisStage, StageResult
from app.stages.pipeline import STAGE_PIPELINE


class AnalysisOrchestrator:
    def __init__(self, stages: list[AnalysisStage] | None = None):
        self.stages = stages if stages is not None else STAGE_PIPELINE

    def run_full_pipeline(
        self, db: Session, creative: Creative
    ) -> tuple[str | None, StageResult]:
        """
        Returns (failed_stage_name, result): failed_stage_name is None and
        result.succeeded is True if every stage succeeded; otherwise
        failed_stage_name names the stage that stopped the pipeline and
        result carries its error.

        Also persists the same information onto the Blueprint itself
        (last_failed_stage / last_failed_stage_error), in lockstep with
        status - this is what makes "why did this fail" answerable later
        from a plain GET, not just from the response of the request that
        triggered the failure. A stage that fails a prerequisite check
        (e.g. "no product assigned") correctly creates no AnalysisRun, so
        AnalysisRun history alone can never reconstruct this after the
        fact - it has to be written down at the moment it happens.
        """
        blueprint = creative.blueprint

        # queued -> analyzing happens back-to-back here since V1 has no
        # real async worker yet (plan §11, step 2's note) - the states
        # are still recorded in order so the vocabulary and DB history
        # are consistent for when a real queue/worker is introduced later.
        blueprint.status = STATUS_QUEUED
        db.commit()

        blueprint.status = STATUS_ANALYZING
        db.commit()

        for stage in self.stages:
            result = stage.run(db, creative, blueprint)
            if not result.succeeded:
                blueprint.status = STATUS_FAILED
                blueprint.last_failed_stage = stage.name
                blueprint.last_failed_stage_error = result.error
                db.commit()
                return stage.name, result

        blueprint.status = STATUS_READY
        blueprint.last_failed_stage = None
        blueprint.last_failed_stage_error = None
        db.commit()
        return None, StageResult(succeeded=True)

    def run_single_stage(
        self, db: Session, creative: Creative, stage_name: str
    ) -> StageResult:
        """Reruns exactly one stage without touching any other (plan §6.2)."""
        stage = next((s for s in self.stages if s.name == stage_name), None)
        if stage is None:
            raise ValueError(f"Unknown stage '{stage_name}'")

        blueprint = creative.blueprint
        blueprint.status = STATUS_ANALYZING
        db.commit()

        result = stage.run(db, creative, blueprint)
        blueprint.status = STATUS_READY if result.succeeded else STATUS_FAILED
        blueprint.last_failed_stage = None if result.succeeded else stage.name
        blueprint.last_failed_stage_error = None if result.succeeded else result.error
        db.commit()

        return result


default_orchestrator = AnalysisOrchestrator()
