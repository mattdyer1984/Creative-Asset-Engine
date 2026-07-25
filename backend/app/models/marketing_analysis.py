"""
MarketingAnalysis — the Analysis Artifact produced by the Marketing
Analysis Stage (plan §6.3, §6.5, §9).

A real AI pass over the Creative Fingerprint's structured JSON (a
text-only prompt, not vision) - not a computed/derived view. Owned by
Slideshow, since marketing analysis is a slideshow-scoped artifact, not
a per-slide one. is_current is scoped accordingly. The legacy
creative_id column (Phase 2.3's transitional dual-FK) was dropped in
Phase 2.8, see MIGRATION_PLAN.md.

creative_fingerprint_id (Phase 7.3 of the Narrative pass, see
MIGRATION_PLAN.md) is a real gap fix, not new functionality: this
artifact is generated *from* a CreativeFingerprint but, unlike
CreativeSpecification (which has always recorded its own two upstream
versions - see that model's docstring), never recorded which one. A
real prerequisite for Phase 7.4's dependency-aware staleness check -
you can't tell whether an artifact is stale relative to its input
without first knowing which input version produced it. Nullable because
existing rows have no way to be backfilled with the truth (the actual
fingerprint used at generation time isn't recoverable after the fact) -
a `None` here means "staleness unknown," not "fresh" or "stale."
"""

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class MarketingAnalysis(Base, AnalysisArtifactMixin):
    __tablename__ = "marketing_analyses"
    __table_args__ = (
        # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
        # "the current marketing analysis for slideshow X" (marketing_analysis_stage.py's
        # own is_current flip).
        Index("ix_marketing_analyses_slideshow_id_is_current", "slideshow_id", "is_current"),
    )

    slideshow_id: Mapped[str | None] = mapped_column(ForeignKey("slideshows.id"), nullable=True)
    creative_fingerprint_id: Mapped[str | None] = mapped_column(
        ForeignKey("creative_fingerprints.id"), nullable=True
    )
    narrative_text: Mapped[str] = mapped_column(Text, nullable=False)
