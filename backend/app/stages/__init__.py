"""Analysis Stage abstraction: interface, concrete stages, and the pipeline (plan §6)."""

from app.stages.base import AnalysisStage, StageResult
from app.stages.pipeline import STAGE_PIPELINE

__all__ = ["AnalysisStage", "StageResult", "STAGE_PIPELINE"]
