"""
Slide — one ordered image within a Slideshow (Phase 2 of the
Slideshow/Slide migration). Replaces Creative as "the thing with an
image and slide-scoped analysis artifacts."

slide_index is always 0 in Phase 2 - this migration is deliberately
cardinality-preserving (exactly one Slide per Slideshow); the column
exists now so true multi-slide import (a later phase) doesn't need
another migration just to add ordering.

Owns the pointers to slide-scoped artifacts (OCR, Creative Fingerprint) -
slideshow-scoped artifacts (Marketing Analysis, Recreation Prompt) are
pointed to from Slideshow instead. Product association is via
ProductAppearance (app.models.product_appearance), not a direct FK -
replacing Creative.product_id's single-product assumption with a proper
many-to-many join.

Additive as of Phase 2.1 - nothing reads or writes this table yet.
"""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._shared import new_uuid


class Slide(Base):
    __tablename__ = "slides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slideshow_id: Mapped[str] = mapped_column(ForeignKey("slideshows.id"), nullable=False)
    slide_index: Mapped[int] = mapped_column(default=0)

    stored_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # Provenance from the Import Provider (plan §5), carried over
    # unchanged from Creative.
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(2048), nullable=False)
    raw_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Pointers to the current version of each slide-scoped artifact.
    current_ocr_result_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_creative_fingerprint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    slideshow: Mapped["Slideshow"] = relationship(back_populates="slides")
    product_appearances: Mapped[list["ProductAppearance"]] = relationship(back_populates="slide")

    @property
    def current_product_appearance(self) -> "ProductAppearance | None":
        """
        The slide's first current ProductAppearance, if any - a
        convenience for API responses that need "is a product assigned,
        and which one" without a separate query (e.g. the Slideshow list
        view, for UI parity with the old Creative.product
        denormalization). Kept exactly as-is (Phase 6 of the multi
        per-slide product detection work, see MIGRATION_PLAN.md, added
        the plural current_product_appearances alongside it rather than
        changing this one's behavior - same non-breaking pattern as
        Phase 4.1's Slideshow.primary_slide).
        """
        return next((a for a in self.product_appearances if a.is_current), None)

    @property
    def current_product_appearances(self) -> list["ProductAppearance"]:
        """
        Every current ProductAppearance on this slide - Phase 6's actual
        "zero, one, or several products per slide" support. Unlike
        current_product_appearance above, this was never a single-item
        invariant to begin with (ProductAppearance has supported this
        structurally since Phase 2.1) - just nothing consumed more than
        the first one until now.
        """
        return [a for a in self.product_appearances if a.is_current]
