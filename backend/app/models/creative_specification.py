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
"""

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CreativeSpecification(Base, AnalysisArtifactMixin):
    __tablename__ = "creative_specifications"

    slideshow_id: Mapped[str | None] = mapped_column(ForeignKey("slideshows.id"), nullable=True)
    product_lock_profile_id: Mapped[str] = mapped_column(
        ForeignKey("product_lock_profiles.id"), nullable=False
    )
    creative_fingerprint_id: Mapped[str] = mapped_column(
        ForeignKey("creative_fingerprints.id"), nullable=False
    )
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
