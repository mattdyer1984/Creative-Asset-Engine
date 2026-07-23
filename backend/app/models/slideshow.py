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

    # Phase 10.5 (AI Creative Engine vNext, see MIGRATION_PLAN.md's ADR
    # §4b) - which EvidenceSource (one ImportProvider call) produced this
    # Slideshow. Nullable: every Slideshow created before this phase, and
    # any future direct/manual creation path, has none. Many-to-one - a
    # group_as_one=False multi-file import shares one EvidenceSource
    # across every resulting Slideshow, matching EvidencePackage's own
    # one-package-many-media_assets shape.
    evidence_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_sources.id"), nullable=True
    )

    imported_at: Mapped[datetime] = mapped_column(default=utcnow)

    status: Mapped[str] = mapped_column(String(32), default=STATUS_IMPORTED)

    # Pointers to the current version of each slideshow-scoped artifact.
    # Slide-scoped artifacts (OCR, Creative Fingerprint) are pointed to
    # from Slide instead - see app.models.slide.
    current_marketing_analysis_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Renamed from current_recreation_prompt_id in Phase 8.1 of the
    # Generation -> Validation proof of loop (see MIGRATION_PLAN.md).
    current_creative_specification_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    # Phase 7.2 (Narrative pass, see MIGRATION_PLAN.md) - additive,
    # same pattern as the two pointers above.
    current_narrative_structure_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

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
    def primary_slide(self) -> "Slide":
        """
        The Slide the analysis Stages read/write (always slides[0]) -
        renamed from the old `.slide` (Phase 2-2.7's 1:1-only accessor,
        which raised if a Slideshow ever had more than one Slide) as part
        of Phase 4 (true multi-slide import, see MIGRATION_PLAN.md).

        Deliberately still single-slide-scoped, not a loop over every
        Slide: Phase 4's own scope is "a Slideshow can legitimately have
        N Slides," not "the Stages analyze every Slide" - that's Phase
        5's job (optional multi per-slide product detection). Every
        existing Slideshow is still exactly 1:1 until Phase 4.2's import
        grouping lands, so this returns the exact same value `.slide`
        did for every Slideshow that exists today.

        Only raises if `slides` is empty - a Slideshow should never have
        zero Slides, that invariant is still worth enforcing loudly.
        """
        if not self.slides:
            raise ValueError(f"Slideshow {self.id} has no Slides")
        return self.slides[0]
