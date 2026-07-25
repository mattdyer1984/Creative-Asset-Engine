"""
GenerationLog — Phase 12 (Human Feedback & Learning System, see
MIGRATION_PLAN.md). One row per call to POST .../generate-creative,
created in app.routers.slideshows.generate_creative *after*
generate_with_retry returns, from the RetryLoopResult it already has in
hand - no changes needed to generate_with_retry.py/generation_engine.py/
decision_engine.py themselves. Deliberately one row per *call*, not one
row per GenerationAttempt: a call can internally retry (chaining
several GenerationAttempt rows via retry_of_generation_attempt_id)
before returning a winner or giving up, and the id this model mints is
the permanent "Generation UUID" the spec asks everything (images,
prompt, blueprint, product, review, future regenerations, and the
on-disk archive folder) to reference - one id per what the human
experiences as one Generate action, not one per internal retry.

winning_generated_image_id/final_output_id are both nullable - no
candidate passing quality across every retry is a real, honest outcome
this codebase has handled explicitly since Phase 11.4/11.8, not an
error state.

product_id (single/primary product) and bundle_product_ids_json (Bundle
Composition) are mutually exclusive, mirroring the same single-vs-
plural duality QualityAssessment.image_validation_result_id/_ids
already established for the identical single-product-vs-bundle split.
Both, plus project_id, are denormalized here from the slideshow/product
appearance rather than requiring a join at query time - the spec's own
"highest/lowest scoring, product-specific, average scores" query needs
call for it.

archive_path points at this call's self-contained
Generation Logs/{created_at:%Y-%m-%d_%H-%M-%S}/ folder on disk (see
app.services.generation_log_archive) - the archive is the permanent,
reproducible snapshot; this row is the searchable index over it.
"""

from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class GenerationLog(Base):
    __tablename__ = "generation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slideshow_id: Mapped[str] = mapped_column(ForeignKey("slideshows.id"), nullable=False)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
    # only product_id has a confirmed, real filter query
    # (routers/generation_logs.py's list endpoint); slideshow_id/slide_id/
    # project_id have no confirmed filter query anywhere in this codebase
    # today, so left un-indexed per "don't add indexes blindly."
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    bundle_product_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    winning_generated_image_id: Mapped[str | None] = mapped_column(
        ForeignKey("generated_images.id"), nullable=True
    )
    final_output_id: Mapped[str | None] = mapped_column(ForeignKey("final_outputs.id"), nullable=True)
    quality_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    creativity_level: Mapped[str] = mapped_column(String(32), nullable=False)
    text_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    creative_specification_id: Mapped[str] = mapped_column(
        ForeignKey("creative_specifications.id"), nullable=False
    )
    creative_specification_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    archive_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
