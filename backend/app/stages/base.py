"""
AnalysisStage interface (plan §6.1).

Every stage in STAGE_PIPELINE implements this. The Orchestrator (§6.2)
only ever calls stage.run(db, creative, blueprint) and looks at the
returned StageResult - it has no idea what a given stage does internally.
"""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint


@dataclass
class StageResult:
    succeeded: bool
    error: str | None = None  # set only when succeeded=False


class AnalysisStage(Protocol):
    name: str  # unique key, e.g. "ocr" - matches AnalysisRun.analysis_type

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        """
        - Reads whatever prior-stage outputs it depends on (via the
          Blueprint's current_*_id pointers).
        - Writes its own new AnalysisRun + Analysis Artifact row(s) -
          never mutates a previous version.
        - Updates the one Blueprint field it owns, if it owns one.
        - Never raises for expected failure modes (a provider error, a
          missing prerequisite) - those come back as
          StageResult(succeeded=False, error=...). Raising is reserved
          for genuine bugs.
        """
        ...
