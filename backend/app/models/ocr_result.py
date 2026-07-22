"""
OCRResult — the Analysis Artifact produced by the OCR Stage (plan §6.5, §7).

is_current is scoped to creative_id (legacy) / slide_id (Phase 2+): at
most one OCRResult per creative/slide has is_current=True at any time.

Transitional (Phase 2.3 of the Slideshow/Slide migration): both
creative_id and slide_id exist. creative_id remains authoritative,
written by the old pipeline, until Phase 2.7; slide_id is backfilled
here and written by the new pipeline from Phase 2.4 onward. Both are
nullable so new rows written by either pipeline don't need the other.
"""

from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class OCRResult(Base, AnalysisArtifactMixin):
    __tablename__ = "ocr_results"

    creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured_blocks_json: Mapped[list] = mapped_column(JSON, default=list)
