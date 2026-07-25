"""
AnalysisRun — the traceability backbone (plan §6.5, §7).

Records HOW an Analysis Artifact was produced (provider, model, status).
The artifact itself (OCRResult, etc.) records WHAT was produced and holds
its own analysis_run_id pointing back here — the relating direction is
artifact -> run, not run -> artifact, since some stages (Product
Isolation) produce more than one artifact row per run.

A run's slide_id is populated for slide-scoped analysis_types (ocr,
product_isolation, product_lock_profile, creative_fingerprint);
slideshow_id for slideshow-scoped ones (marketing_analysis,
creative_specification) - mirroring exactly which artifact table each
analysis_type uses. The legacy creative_id column (Phase 2.3's
transitional dual-FK) was dropped in Phase 2.8, see MIGRATION_PLAN.md.
"""

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
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
# Phase 10.4 of AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
# §8) - part of SLIDESHOW_STAGE_PIPELINE like every other analysis
# artifact above it (unlike GENERATED_IMAGE/IMAGE_VALIDATION below,
# this is an analysis pass, not a paid generation/validation action).
ANALYSIS_TYPE_SCENE_INTELLIGENCE = "scene_intelligence"
# Phase 8.3 of the Generation -> Validation proof of loop (see
# MIGRATION_PLAN.md) - deliberately not added to SLIDESHOW_STAGE_PIPELINE;
# see app.slideshow_stages.image_generation_stage's docstring for why.
ANALYSIS_TYPE_GENERATED_IMAGE = "generated_image"
# Phase 8.4 - same "not in SLIDESHOW_STAGE_PIPELINE" reasoning as
# ANALYSIS_TYPE_GENERATED_IMAGE above.
ANALYSIS_TYPE_IMAGE_VALIDATION = "image_validation"

STATUS_PENDING = "pending"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
    # both real, confirmed query shapes (routers/slideshows.py's
    # AnalysisRun history endpoint, timing_report.py) - SQLite doesn't
    # auto-index foreign keys the way Postgres does, so these were full
    # table scans without this.
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True, index=True)
    slideshow_id: Mapped[str | None] = mapped_column(
        ForeignKey("slideshows.id"), nullable=True, index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(16), default="1.0")

    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    # Optimisation & Stability Pass, Tier 2 (see MIGRATION_PLAN.md) - no
    # timing or cost instrumentation existed anywhere in the pipeline
    # before this; stamped by mark_succeeded/mark_failed
    # (app.stages.execution), the two functions every Stage already
    # calls, so no Stage needs its own bookkeeping to get this "for
    # free." All nullable: every pre-existing row genuinely has none of
    # this data, and a null value on an old row is simply "not measured
    # yet," not a bug to design around - the same "every pre-this-phase
    # row genuinely has none" pattern this codebase already uses
    # elsewhere (see e.g. GeneratedImage.generation_reference_set_id's
    # own docstring).
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The AI-provider network call specifically, timed by the calling
    # Stage around its own provider.method(...) call (time.perf_counter())
    # - `duration_ms - provider_call_ms` is DB/overhead time "where
    # practical," an approximation, not a full APM trace.
    provider_call_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # USD, computed from backend/pricing.yaml (app.services.cost_estimation)
    # at the same point finished_at/duration_ms are stamped - null
    # whenever pricing.yaml has no entry for this run's provider/model,
    # not a guessed value.
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
