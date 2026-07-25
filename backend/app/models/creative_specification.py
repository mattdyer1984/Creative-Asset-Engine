"""
CreativeSpecification — the Analysis Artifact produced by the Creative
Specification Stage (plan §6.3, §6.5, §10).

Renamed from RecreationPrompt in Phase 8.1 of the Generation ->
Validation proof of loop (see MIGRATION_PLAN.md): once an actual
ImageGenerationProvider exists, "prompt" is ambiguous - this is the
provider-neutral creative intent (subject, composition, style - what
should be created), not the compiled, provider-specific string sent to
an image generation API. That compiled string is persisted only as
GeneratedImage.prompt_used metadata, never as its own canonical entity.

Owned by Slideshow (a slideshow-scoped artifact). is_current is scoped
accordingly. Unlike the slide-scoped artifacts, this one explicitly
records which ProductLockProfile and CreativeFingerprint VERSIONS it was
composed from (plan §7's key design point) - a CreativeSpecification is
meaningless without knowing exactly which upstream versions produced it.

The legacy creative_id column (Phase 2.3's transitional dual-FK) was
dropped in Phase 2.8, see MIGRATION_PLAN.md.

Real-world-diagnosed fix (Generate All, see MIGRATION_PLAN.md): a real
Generate All run showed slide 2's generated image was built from slide
1's own scene (a genuine cross-slide contamination bug) - this was one
row per Slideshow, always built from the *primary* slide's own Creative
Fingerprint (creative_specification_stage.py), so every slide's
generation silently shared the primary slide's spec regardless of which
slide's image was actually being produced. `slide_id` added below,
mirroring CreativeFingerprint's own slide_id (nullable for the same
reason - historical rows predate this fix and can't retroactively know
which slide they were "really" for beyond what's backfilled via
creative_fingerprint_id -> creative_fingerprints.slide_id). `slideshow_id`
is kept (still useful - "every spec ever built for this slideshow").
"""

from sqlalchemy import ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CreativeSpecification(Base, AnalysisArtifactMixin):
    __tablename__ = "creative_specifications"
    __table_args__ = (
        # Optimisation & Stability Pass, Tier 3.1 (see MIGRATION_PLAN.md) -
        # "the current spec for slide X" (creative_specification_stage.py's
        # own is_current flip, plus generation_engine.py/generate_with_retry.py).
        Index("ix_creative_specifications_slide_id_is_current", "slide_id", "is_current"),
    )

    slideshow_id: Mapped[str | None] = mapped_column(ForeignKey("slideshows.id"), nullable=True)
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    product_lock_profile_id: Mapped[str] = mapped_column(
        ForeignKey("product_lock_profiles.id"), nullable=False
    )
    creative_fingerprint_id: Mapped[str] = mapped_column(
        ForeignKey("creative_fingerprints.id"), nullable=False
    )
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
