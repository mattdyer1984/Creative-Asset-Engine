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
"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class MarketingAnalysis(Base, AnalysisArtifactMixin):
    __tablename__ = "marketing_analyses"

    creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    slideshow_id: Mapped[str | None] = mapped_column(ForeignKey("slideshows.id"), nullable=True)
    narrative_text: Mapped[str] = mapped_column(Text, nullable=False)
