"""
OCRResult — the Analysis Artifact produced by the OCR Stage (plan §6.5, §7).

is_current is scoped to slide_id: at most one OCRResult per slide has
is_current=True at any time. The legacy creative_id column (Phase 2.3's
transitional dual-FK) was dropped in Phase 2.8, see MIGRATION_PLAN.md.
"""

from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class OCRResult(Base, AnalysisArtifactMixin):
    __tablename__ = "ocr_results"

    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured_blocks_json: Mapped[list] = mapped_column(JSON, default=list)
