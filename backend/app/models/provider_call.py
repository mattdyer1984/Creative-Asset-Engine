"""
ProviderCall — one row per billable AI provider call (Phase 1
remediation, WP-2).

**Why this is not just more columns on AnalysisRun.** AnalysisRun cannot
carry per-call usage, for two verified reasons:

1. It is *provenance-bearing*. Every analysis artifact FKs to it
   (`_analysis_artifact_mixin.analysis_run_id`, required), and
   `ProductReferenceImage.analysis_run_id` specifically means "the run
   that acquired this image". `reference_scoring_stage.py`'s own
   docstring already documents deliberately NOT creating runs there,
   because overwriting that field "would destroy that provenance".
2. It is *stage-scoped, not call-scoped*. `image_validation_stage.py`
   opens ONE run and then makes TWO provider calls under it (Stage 1
   identity, then Stage 2 creative). Folding both into one row either
   double-counts or loses per-call attribution.

So AnalysisRun keeps its job (a stage ran, here is its wall-clock and
its artifacts) and this table takes the billing job (one paid call, one
row). The correlation FKs below are all nullable because several real
paid calls belong to no AnalysisRun at all - photorealism scoring,
reference scoring, creative intelligence and text intelligence were
completely invisible to cost reporting before this table existed.

**cost_status vs record_source are two orthogonal axes**, deliberately
not merged into one enum:

  cost_status   how far to trust the number - exact | estimated |
                partial | unknown (see services/cost_estimation.py).
  record_source where the row came from - `per_call` for genuine rows
                created going forward, `legacy_aggregate` for rows
                reconstructed from historical AnalysisRun data.

A legacy row can still have perfectly sound cost data, and a per_call
row can still be `partial`, so collapsing these would make it impossible
to ask "show me all under-counted rows" without also filtering
provenance. Reporting excludes `legacy_aggregate` cleanly via
`record_source`.

A `legacy_aggregate` row must never be read as one exact provider call:
the AnalysisRun it came from may have covered one call, several calls,
aggregated usage, or incomplete usage - which is precisely why it is
labelled rather than silently mixed in.
"""

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow

RECORD_SOURCE_PER_CALL = "per_call"
RECORD_SOURCE_LEGACY_AGGREGATE = "legacy_aggregate"


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    __table_args__ = (
        # Daily spend rollups and the spend cap both scan by date.
        Index("ix_provider_calls_created_at", "created_at"),
        # "what did this stage cost" - the two-calls-one-run case.
        Index("ix_provider_calls_analysis_run_id", "analysis_run_id"),
        # "what did this slideshow / slide cost" - the reporting axes
        # WP-2 requires.
        Index("ix_provider_calls_slideshow_id", "slideshow_id"),
        Index("ix_provider_calls_slide_id", "slide_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    # --- what was called -------------------------------------------
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    # What the provider says it actually served - aliases
    # (gemini-flash-latest) and dated snapshots (gpt-5.5-2026-04-23)
    # differ from what we request, and spend should attribute to the
    # real thing. Null when the provider does not report it.
    reported_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # The billing axis (ocr, vision_analysis, image_generation, ...),
    # deliberately distinct from AnalysisRun.analysis_type, which is a
    # pipeline-stage axis - one stage can make calls of two capabilities.
    capability: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- prompt identity (populated by WP-3; null until then) -------
    prompt_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- usage ------------------------------------------------------
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Image-billed calls report a count, not tokens.
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- cost -------------------------------------------------------
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Required whenever status is partial/unknown - an unqualified
    # "partial" is useless when auditing later.
    cost_status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- provenance --------------------------------------------------
    record_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RECORD_SOURCE_PER_CALL
    )

    # --- correlation (all nullable - not every call has every context) --
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=True
    )
    generated_image_id: Mapped[str | None] = mapped_column(
        ForeignKey("generated_images.id"), nullable=True
    )
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    slideshow_id: Mapped[str | None] = mapped_column(ForeignKey("slideshows.id"), nullable=True)
