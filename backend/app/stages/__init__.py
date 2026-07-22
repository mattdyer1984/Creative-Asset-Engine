"""
Shared stage-execution infrastructure: StageResult (base.py) and
start_analysis_run/mark_failed/mark_succeeded (execution.py). The old
pipeline's concrete stages, STAGE_PIPELINE, and the AnalysisStage
Protocol were removed during the Phase 2 migration and its subsequent
engineering review - what remains here is used exclusively by
app.slideshow_stages now.
"""

from app.stages.base import StageResult

__all__ = ["StageResult"]
