"""
CreativeFingerprint — the Analysis Artifact produced by the Creative
Fingerprint Stage (plan §6.3, §6.5, §9).

Owned by Creative (legacy) / Slide (Phase 2+). is_current is scoped
accordingly: at most one CreativeFingerprint per creative/slide has
is_current=True at any time.

Transitional (Phase 2.3 of the Slideshow/Slide migration) - see
OCRResult's docstring for the creative_id/slide_id coexistence pattern,
identical here.

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

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CreativeFingerprint(Base, AnalysisArtifactMixin):
    __tablename__ = "creative_fingerprints"

    creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    ocr_result_id: Mapped[str | None] = mapped_column(ForeignKey("ocr_results.id"), nullable=True)
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
