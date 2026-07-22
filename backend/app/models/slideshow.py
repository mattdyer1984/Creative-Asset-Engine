"""
Slideshow — the primary marketing unit (replaces Creative + CreativeBlueprint
as the top-level entity; see Phase 2 of the Slideshow/Slide migration).

Owns the import-level identity (project_id, imported_at, source
provenance) and the pipeline lifecycle (status, current_*_id pointers
for slideshow-scoped artifacts, last_failed_stage/error) that used to
live on CreativeBlueprint. An ordered sequence of Slides (see
app.models.slide) - in Phase 2 always exactly one, since this migration
is deliberately cardinality-preserving; true multi-slide import is a
later phase.

Additive as of Phase 2.1 - nothing reads or writes this table yet.
Backfilled from existing Creative/CreativeBlueprint rows in Phase 2.2.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._shared import new_uuid, utcnow

# Same lifecycle vocabulary as the old CreativeBlueprint.status (plan
# §6), carried over unchanged: imported -> queued -> analyzing -> ready|failed.
STATUS_IMPORTED = "imported"
STATUS_QUEUED = "queued"
STATUS_ANALYZING = "analyzing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


class Slideshow(Base):
    __tablename__ = "slideshows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # Optional organisational grouping - not required (plan §1, §6),
    # carried over unchanged from Creative.project_id.
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)

    imported_at: Mapped[datetime] = mapped_column(default=utcnow)

    status: Mapped[str] = mapped_column(String(32), default=STATUS_IMPORTED)

    # Pointers to the current version of each slideshow-scoped artifact.
    # Slide-scoped artifacts (OCR, Creative Fingerprint) are pointed to
    # from Slide instead - see app.models.slide.
    current_marketing_analysis_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_recreation_prompt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    last_failed_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_failed_stage_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provenance from the Import Provider (plan §5), carried over
    # unchanged from CreativeBlueprint.source_references_json.
    source_references_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Empty in V1; placeholder for future image-generation outputs -
    # carried over unchanged from CreativeBlueprint.
    future_generated_assets_json: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    slides: Mapped[list["Slide"]] = relationship(
        back_populates="slideshow", order_by="Slide.slide_index", cascade="all, delete-orphan"
    )

    @property
    def slide(self) -> "Slide":
        """
        The single Slide - a convenience for the new pipeline (Phase 2.4
        onward), valid only while cardinality stays 1:1 (Phase 2's
        invariant; true multi-slide import is a later phase). Raises
        loudly rather than silently picking slides[0] if that invariant
        is ever violated, since a caller relying on this accessor has no
        other way to notice.
        """
        if len(self.slides) != 1:
            raise ValueError(
                f"Slideshow.slide assumes exactly one Slide (Phase 2 invariant); "
                f"found {len(self.slides)} for slideshow {self.id}"
            )
        return self.slides[0]
