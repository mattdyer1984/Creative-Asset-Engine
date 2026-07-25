"""
ImageValidationResult — the Analysis Artifact produced by the Image
Validation Stage (Phase 8.4 of the Generation -> Validation proof of
loop, see MIGRATION_PLAN.md).

Closes the loop: a GeneratedImage (Phase 8.3) gets judged against the
canonical Product Profile's immutable fields, one judgment per field
(field_checks_json), plus a computed `passed` (all fields preserved -
computed in code, never asked of the AI as a bare boolean, per the
architecture direction) and one `overall_explanation`. This is the
"explain why it failed" the user explicitly asked for - field_checks is
surfaced directly by the frontend (Phase 8.5), not summarized away.

product_id is stored directly (not re-derived via
generated_image -> creative_specification -> product_lock_profile each
time it's needed) - the same product a GeneratedImage's Creative
Specification was built around, recorded once at validation time for
straightforward querying.

identity_passed / identity_checks_json (Phase 9.1 of Product Lock v2,
see MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §1/§7) are
Stage 1 Identity Validation's output - short-circuiting, visual-identity
checks against the same GenerationReferenceSet used to generate,
distinct from this table's original per-field Stage 2 creative checks.
Both nullable for the same pre-this-phase-row reason as everything else
in this migration. `passed`/`field_checks_json` are repurposed in
meaning, not shape, from this phase onward: `passed` becomes "identity
passed AND creative passed," `field_checks_json` continues to mean the
Stage 2 creative checks specifically - no column renamed, no shape
changed, only what the existing columns mean once both stages exist.
"""

from sqlalchemy import Boolean, ForeignKey, Index, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class ImageValidationResult(Base, AnalysisArtifactMixin):
    __tablename__ = "image_validation_results"
    __table_args__ = (
        # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
        # "the current validation result for generated image X" is the
        # dominant, confirmed query shape (image_validation_stage.py,
        # quality_engine.py, the slideshows router) - product_id is only
        # ever an additional filter on top of this, on the Bundle
        # Composition path, never the leading column.
        Index("ix_image_validation_results_generated_image_id_is_current", "generated_image_id", "is_current"),
    )

    generated_image_id: Mapped[str] = mapped_column(
        ForeignKey("generated_images.id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    field_checks_json: Mapped[list] = mapped_column(JSON, nullable=False)
    overall_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    identity_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    identity_checks_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
