"""
OCRResult — the Analysis Artifact produced by the OCR Stage (plan §6.5, §7).

is_current is scoped to creative_id: at most one OCRResult per creative
has is_current=True at any time.
"""

from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class OCRResult(Base, AnalysisArtifactMixin):
    __tablename__ = "ocr_results"

    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured_blocks_json: Mapped[list] = mapped_column(JSON, default=list)
