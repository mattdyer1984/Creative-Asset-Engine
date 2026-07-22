"""
ProductReferenceImage — the Analysis Artifact produced by the Product
Isolation Stage (plan §6.3, §6.5, §7).

Owned by Product, not by ProductLockProfile or Creative - this is what
lets reference images accumulate and stay reusable across every creative
that features the same product (plan guiding principle 5), and what
makes the Product Isolation Stage independently rerunnable without a
ProductLockProfile needing to exist first.

is_current is scoped to product_id: at any time, the "current" set of
reference images for a product is every row with is_current=True and
that product_id (there can be more than one - a single isolation run can
produce several bounding boxes/crops).

source_creative_id / source_slide_id records which creative's/slide's
image this particular crop came from - provenance, not ownership (plan
§7's comment on this field).

Transitional (Phase 2.3 of the Slideshow/Slide migration): both
source_creative_id and source_slide_id exist, both nullable - see
OCRResult's docstring for why.

source_product_source_import_id (Phase 5.1 of Product Intelligence, see
MIGRATION_PLAN.md) is a third, equally-nullable provenance column for
images sourced from a Product Source (a URL import - the generic
schema.org/OpenGraph fallback, or a platform-specific adapter) rather
than cropped from a creative. Reuses this table rather than inventing a
separate "official image" concept, exactly like source_slide_id reused
it instead of inventing a new one for the new pipeline in Phase 2.3.

analysis_run_id (from AnalysisArtifactMixin) is overridden here to be
nullable, unlike every other artifact that uses the mixin - a Product
Source fetch isn't an AI call, so a URL-sourced row has no AnalysisRun
to point at (same reasoning as ProductSourceImport itself not using this
mixin at all). Rows produced by the Product Isolation Stage continue to
always populate it; only URL-sourced rows leave it null. The mixin
itself stays unchanged for the other five artifact types, which remain
exclusively AI-analysis-derived and should keep requiring a real run.
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class ProductReferenceImage(Base, AnalysisArtifactMixin):
    __tablename__ = "product_reference_images"

    analysis_run_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_runs.id"), nullable=True)

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    source_creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    source_slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    source_product_source_import_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_source_imports.id"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    isolation_method: Mapped[str] = mapped_column(String(64), nullable=False)
