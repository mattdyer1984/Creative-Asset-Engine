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
"""

from sqlalchemy import Boolean, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class ImageValidationResult(Base, AnalysisArtifactMixin):
    __tablename__ = "image_validation_results"

    generated_image_id: Mapped[str] = mapped_column(
        ForeignKey("generated_images.id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    field_checks_json: Mapped[list] = mapped_column(JSON, nullable=False)
    overall_explanation: Mapped[str] = mapped_column(Text, nullable=False)
