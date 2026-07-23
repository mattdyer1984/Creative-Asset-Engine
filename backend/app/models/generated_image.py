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
"""

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class GeneratedImage(Base, AnalysisArtifactMixin):
    __tablename__ = "generated_images"

    slideshow_id: Mapped[str] = mapped_column(ForeignKey("slideshows.id"), nullable=False)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False)
    creative_specification_id: Mapped[str] = mapped_column(
        ForeignKey("creative_specifications.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_used: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generation_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
