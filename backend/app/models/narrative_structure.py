"""
NarrativeStructure — the Analysis Artifact produced by the Narrative
Structure Stage (Phase 7.2 of the Narrative pass, see MIGRATION_PLAN.md's
architecture direction for this phase).

Owned by Slideshow (a slideshow-scoped artifact, like MarketingAnalysis/
RecreationPrompt - no legacy Creative-scoped equivalent exists, this is
new work, not a migrated old stage). is_current is scoped accordingly.

Explicitly records which OCR result VERSIONS (one per slide, in
slide_index order) it was composed from, via ocr_result_ids_json - same
"an artifact is meaningless without knowing exactly which upstream
versions produced it" principle RecreationPrompt already established for
its own two dependencies (see that model's docstring), just as a JSON
list instead of individual FK columns since the count varies per
slideshow (one per slide, not a fixed small number). This is exactly
what Phase 7.4's dependency-aware staleness check needs: compare this
list against each slide's *current* current_ocr_result_id to tell
whether any slide's OCR has moved on since this was generated.

structured_json shape: {"slides": [{"slide_id": str, "beat": "hook" |
"story" | "reveal" | "proof" | "cta" | "other" | "unclassifiable"}, ...],
"arc_summary": str}.
"""

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class NarrativeStructure(Base, AnalysisArtifactMixin):
    __tablename__ = "narrative_structures"

    slideshow_id: Mapped[str] = mapped_column(ForeignKey("slideshows.id"), nullable=False)
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    ocr_result_ids_json: Mapped[list] = mapped_column(JSON, default=list)
