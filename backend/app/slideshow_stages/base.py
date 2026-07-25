"""
SlideshowAnalysisStage - the Stage interface every analysis stage
implements.

Operates on a Slideshow directly, rather than a Creative+CreativeBlueprint
pair. Slide-scoped stages (OCR, Product Isolation, Product Lock Profile,
Creative Fingerprint, Scene Intelligence, Creative Specification) loop
internally over every Slide in slideshow.slides (Generate All widened
the last few of these from an earlier slideshow.primary_slide-only
design - see each stage's own module docstring for when/why) and write
their own per-slide artifact pointer (Slide.current_*_id). Genuinely
slideshow-wide stages (Marketing Analysis, Narrative Structure) operate
on the Slideshow itself and write Slideshow.current_*_id.

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
