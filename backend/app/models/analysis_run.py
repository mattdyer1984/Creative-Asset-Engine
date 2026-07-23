"""
AnalysisRun — the traceability backbone (plan §6.5, §7).

Records HOW an Analysis Artifact was produced (provider, model, status).
The artifact itself (OCRResult, etc.) records WHAT was produced and holds
its own analysis_run_id pointing back here — the relating direction is
artifact -> run, not run -> artifact, since some stages (Product
Isolation) produce more than one artifact row per run.

Transitional (Phase 2.3 of the Slideshow/Slide migration): creative_id,
slide_id, and slideshow_id all exist, all nullable. A run's slide_id is
populated for slide-scoped analysis_types (ocr, product_isolation,
product_lock_profile, creative_fingerprint); slideshow_id for
slideshow-scoped ones (marketing_analysis, creative_specification) - mirroring
exactly which artifact table each analysis_type's own Phase 2.3 split
uses. creative_id remains authoritative until Phase 2.7.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow

# One value per Stage in STAGE_PIPELINE (plan §6). Adding a future stage
# (Brand Analysis, Compliance Analysis, ...) means adding a new value here.
ANALYSIS_TYPE_OCR = "ocr"
ANALYSIS_TYPE_PRODUCT_ISOLATION = "product_isolation"
ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE = "product_lock_profile"
ANALYSIS_TYPE_CREATIVE_FINGERPRINT = "creative_fingerprint"
ANALYSIS_TYPE_MARKETING_ANALYSIS = "marketing_analysis"
ANALYSIS_TYPE_CREATIVE_SPECIFICATION = "creative_specification"
ANALYSIS_TYPE_NARRATIVE_STRUCTURE = "narrative_structure"
# Phase 8.3 of the Generation -> Validation proof of loop (see
# MIGRATION_PLAN.md) - deliberately not added to SLIDESHOW_STAGE_PIPELINE;
# see app.slideshow_stages.image_generation_stage's docstring for why.
ANALYSIS_TYPE_GENERATED_IMAGE = "generated_image"

STATUS_PENDING = "pending"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    slideshow_id: Mapped[str | None] = mapped_column(ForeignKey("slideshows.id"), nullable=True)
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(16), default="1.0")

    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
