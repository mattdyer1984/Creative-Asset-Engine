"""
GeneratedImage — the Analysis Artifact produced by the Image Generation
Stage (Phase 8.3 of the Generation -> Validation proof of loop, see
MIGRATION_PLAN.md).

Unlike the other Analysis Artifacts, this one isn't itself an "analysis"
of anything - it's the generated candidate image the Validation Stage
(Phase 8.4) will analyze. Kept on the exact same AnalysisArtifactMixin
shape anyway (id/analysis_run_id/schema_version/is_current/created_at)
for consistency: a regenerate is just another version, same is_current
versioning every other artifact already uses, not a special case.

No new architecture beyond the mixin - `provider`/`model_name`/
`prompt_used`/`seed`/`generation_time_seconds` are exactly the
structured metadata ImageGenerationProvider.generate_image returns
(app.ai_providers.base.GeneratedImageResult), persisted verbatim so a
generated image's provenance is always inspectable later, the same
"record the attempt, including how it was made" discipline this
project uses throughout. `file_path` follows ProductReferenceImage's
exact convention (owning-entity-keyed local storage, see app.storage).

Deliberately scoped to one slide, not the whole Slideshow, per the
Phase 8 architecture direction ("generate one slide first, not an
entire slideshow") - slide_id is non-nullable, unlike the slideshow-
scoped artifacts (MarketingAnalysis, CreativeSpecification) which have
no slide_id at all.

generation_reference_set_id (Phase 9.1 of Product Lock v2, see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §1) records
which specific GenerationReferenceSet's images were actually sent to
the provider for this generation - nullable because every row created
before this ADR shipped genuinely has none (a pre-Product-Lock-v2
generation used no reference images at all), and because this is a
hard prerequisite for new generations (§6 of that ADR), not an optional
enhancement, so a null value on a *new* row would itself be a bug, not
a valid state to design around.

generation_attempt_id / candidate_index (Phase 10.2 of AI Creative
Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext"
§12) record which GenerationAttempt this candidate belongs to, and its
0-based position within that attempt's N candidates - both nullable
for the same "every pre-this-phase row genuinely has none" reason as
generation_reference_set_id above. The original Phase 8.3
single-call `generate-image` endpoint is untouched and keeps producing
rows with both left null - Phase 10.2 is a genuinely new,
candidate-count-aware path alongside it, not a replacement.
"""

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class GeneratedImage(Base, AnalysisArtifactMixin):
    __tablename__ = "generated_images"
    __table_args__ = (
        # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
        # "the current generated image for slide X" is the real, confirmed
        # query shape everywhere this is read (routers, generate_with_retry,
        # image_generation_stage) - never filtered by slideshow_id alone.
        Index("ix_generated_images_slide_id_is_current", "slide_id", "is_current"),
    )

    slideshow_id: Mapped[str] = mapped_column(ForeignKey("slideshows.id"), nullable=False)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False)
    creative_specification_id: Mapped[str] = mapped_column(
        ForeignKey("creative_specifications.id"), nullable=False
    )
    generation_reference_set_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_reference_sets.id"), nullable=True
    )
    generation_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_attempts.id"), nullable=True
    )
    candidate_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_used: Mapped[str] = mapped_column(Text, nullable=False)
    # WP-3: prompt IDENTITY, stored alongside the rendered text rather
    # than instead of it. The two answer different questions and neither
    # replaces the other: `prompt_used` is exactly what this image was
    # asked for, which is what you read when the output looks wrong;
    # these three say which prompt DEFINITION produced it, which is what
    # you group by when comparing many images, or check when asking
    # "was this made before or after we changed the compiler?".
    #
    # Nullable because every image generated before WP-3 genuinely has
    # no known prompt identity - back-filling a guess would be worse
    # than an honest null.
    prompt_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generation_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Optimisation & Stability Pass, Tier 2.2 (see MIGRATION_PLAN.md) -
    # USD, computed from backend/pricing.yaml's per-image rate for this
    # row's provider/model (app.services.cost_estimation) - null when
    # pricing.yaml has no entry for it, not a guessed value. Image
    # generation is billed per-image, not by token, so this has no
    # prompt_tokens/completion_tokens counterpart the way AnalysisRun's
    # does.
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
