"""
StageResult - the shared, entity-agnostic result type every Stage.run()
returns.

The AnalysisStage Protocol that used to live here (run(db, creative,
blueprint) - the old pipeline's 3-arg contract) was removed during the
Phase 2 engineering review: it had zero implementers left once Phase 2.7
deleted the old stages, and its only remaining "consumer" was its own
re-export in app/stages/__init__.py. The current contract is
app.slideshow_stages.base.SlideshowAnalysisStage (run(db, slideshow)).
"""

from dataclasses import dataclass


@dataclass
class StageResult:
    succeeded: bool
    error: str | None = None  # set only when succeeded=False
