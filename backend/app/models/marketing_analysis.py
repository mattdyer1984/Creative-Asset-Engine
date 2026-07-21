"""
MarketingAnalysis — the Analysis Artifact produced by the Marketing
Analysis Stage (plan §6.3, §6.5, §9).

A real AI pass over the Creative Fingerprint's structured JSON (a
text-only prompt, not vision) - not a computed/derived view. Owned by
Creative. is_current is scoped to creative_id.
"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class MarketingAnalysis(Base, AnalysisArtifactMixin):
    __tablename__ = "marketing_analyses"

    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"), nullable=False)
    narrative_text: Mapped[str] = mapped_column(Text, nullable=False)
