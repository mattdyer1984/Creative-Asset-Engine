"""
SlideshowAnalysisStage - the Stage interface every analysis stage
implements.

Operates on a Slideshow directly, rather than a Creative+CreativeBlueprint
pair: slide-scoped stages (OCR, Product Isolation, Product Lock Profile,
Creative Fingerprint) read/write via slideshow.primary_slide - the single
Slide these Stages analyze, even once a Slideshow can have more than one
(Phase 4 onward; see MIGRATION_PLAN.md - looping every Stage over every
Slide is explicitly Phase 5's job, not this accessor's). Slideshow-scoped
stages (Marketing Analysis, Recreation Prompt) operate on the Slideshow
itself.

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
    name: str  # unique key, matches AnalysisRun.analysis_type

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        """
        - Reads whatever prior-stage outputs it depends on (via
          slideshow.primary_slide's or slideshow's own current_*_id
          pointers).
        - Writes its own new AnalysisRun + Analysis Artifact row(s) -
          never mutates a previous version.
        - Updates the one Slide/Slideshow field it owns, if it owns one.
        - Never raises for expected failure modes (a provider error, a
          missing prerequisite) - those come back as
          StageResult(succeeded=False, error=...). Raising is reserved
          for genuine bugs.
        """
        ...
