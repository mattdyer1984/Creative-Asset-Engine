"""
MarketingAnalysis — the Analysis Artifact produced by the Marketing
Analysis Stage (plan §6.3, §6.5, §9).

A real AI pass over the Creative Fingerprint's structured JSON (a
text-only prompt, not vision) - not a computed/derived view. Owned by
Creative (legacy) / Slideshow (Phase 2+, since marketing analysis is a
slideshow-scoped artifact, not a per-slide one). is_current is scoped
accordingly.

Transitional (Phase 2.3 of the Slideshow/Slide migration): both
creative_id and slideshow_id exist, both nullable - see OCRResult's
docstring for why.

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

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class MarketingAnalysis(Base, AnalysisArtifactMixin):
    __tablename__ = "marketing_analyses"

    creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    slideshow_id: Mapped[str | None] = mapped_column(ForeignKey("slideshows.id"), nullable=True)
    creative_fingerprint_id: Mapped[str | None] = mapped_column(
        ForeignKey("creative_fingerprints.id"), nullable=True
    )
    narrative_text: Mapped[str] = mapped_column(Text, nullable=False)
