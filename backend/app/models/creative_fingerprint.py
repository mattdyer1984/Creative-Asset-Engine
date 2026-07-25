"""
CreativeFingerprint — the Analysis Artifact produced by the Creative
Fingerprint Stage (plan §6.3, §6.5, §9).

Owned by Slide. is_current is scoped accordingly: at most one
CreativeFingerprint per slide has is_current=True at any time. The
legacy creative_id column (Phase 2.3's transitional dual-FK) was dropped
in Phase 2.8, see MIGRATION_PLAN.md.

ocr_result_id (Phase 7.4 of the Narrative pass, see MIGRATION_PLAN.md) -
found and fixed while building that sub-phase's staleness service, same
category of gap as MarketingAnalysis.creative_fingerprint_id (7.3): this
stage reads the slide's OCR result as optional enrichment context, but
never recorded which one it actually used. Nullable for two real
reasons, not just legacy-row tolerance: OCR is genuinely optional
enrichment here (a fingerprint generated before OCR ever ran, or with an
OCR result that came back with no text, legitimately has no OCR
provenance to record), and existing pre-7.4 rows can't be truthfully
backfilled either. A None here means "no OCR dependency" or "unknown",
never "stale" - see app.services.staleness.
"""

from sqlalchemy import ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CreativeFingerprint(Base, AnalysisArtifactMixin):
    __tablename__ = "creative_fingerprints"
    __table_args__ = (
        # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
        # "the current fingerprint for slide X" (creative_fingerprint_stage.py's
        # own is_current flip, plus every reader).
        Index("ix_creative_fingerprints_slide_id_is_current", "slide_id", "is_current"),
    )

    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    ocr_result_id: Mapped[str | None] = mapped_column(ForeignKey("ocr_results.id"), nullable=True)
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
