"""
Analysis Stage abstraction: interface + shared execution helper.

The old pipeline's concrete stages and STAGE_PIPELINE were removed in
Phase 2.7 of the Slideshow/Slide migration - AnalysisStage/StageResult
and execution.py's start_analysis_run/mark_failed/mark_succeeded remain
as shared infrastructure, now used exclusively by app.slideshow_stages.
"""

from app.stages.base import AnalysisStage, StageResult

__all__ = ["AnalysisStage", "StageResult"]
