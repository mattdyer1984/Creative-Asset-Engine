"""
GenerationReferenceSet — Phase 9.1 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §3).

Not the Canonical Reference Library (that's a query over
ProductReferenceImage.library_status="included", computed on read - see
that model's docstring) - this is the small, genuinely versioned record
of exactly which Library images Reference Selection chose for one
specific generation call, and why. AnalysisArtifactMixin-shaped like
every other real per-event artifact in this codebase.

generated_image_id is nullable because a GenerationReferenceSet is
created *before* the generation it feeds succeeds (Reference Selection
has to run first to build the prompt) - it gets linked once that
GeneratedImage is actually persisted, same create-then-link ordering
ADR §6 describes.

analysis_run_id (from AnalysisArtifactMixin) is overridden nullable,
same reasoning ProductReferenceImage's URL-sourced rows and
ProductSourceImport already established: Reference Selection isn't
always an AI call (role-keyword matching needs none - only the rarer
TextGenerationProvider-assisted fallback does).
"""

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class GenerationReferenceSet(Base, AnalysisArtifactMixin):
    __tablename__ = "generation_reference_sets"

    analysis_run_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_runs.id"), nullable=True)

    generated_image_id: Mapped[str | None] = mapped_column(
        ForeignKey("generated_images.id"), nullable=True
    )
    selection_method_json: Mapped[dict] = mapped_column(JSON, nullable=False)
