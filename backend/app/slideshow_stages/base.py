"""
SlideshowAnalysisStage interface - the parallel-pipeline equivalent of
app.stages.base.AnalysisStage (Phase 2.4 of the Slideshow/Slide
migration).

Operates on a Slideshow directly, rather than a Creative+CreativeBlueprint
pair: slide-scoped stages (OCR, Product Isolation, Product Lock Profile,
Creative Fingerprint) read/write via slideshow.slide - the 1:1
convenience accessor on Slideshow, valid while Phase 2's cardinality
invariant holds. Slideshow-scoped stages (Marketing Analysis, Recreation
Prompt) operate on the Slideshow itself.

Re-exports StageResult from app.stages.base unchanged rather than
redefining it - it is already entity-agnostic (succeeded/error only), so
there is nothing to duplicate.
"""

from typing import Protocol

from sqlalchemy.orm import Session

from app.models.slideshow import Slideshow
from app.stages.base import StageResult

__all__ = ["StageResult", "SlideshowAnalysisStage"]


class SlideshowAnalysisStage(Protocol):
    name: str  # unique key, matches AnalysisRun.analysis_type - same vocabulary as the old pipeline

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        """Same contract as app.stages.base.AnalysisStage.run - see there for the full docstring."""
        ...
