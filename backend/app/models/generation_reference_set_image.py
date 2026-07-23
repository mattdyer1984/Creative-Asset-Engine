"""
GenerationReferenceSetImage — Phase 9.1 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §3). Join table:
which Library images (ProductReferenceImage rows) a GenerationReferenceSet
actually selected.

product_id is carried explicitly per row, not just inherited from the
parent set - the concrete schema hook that lets one Set span multiple
products later (Bundle Composition, see the vNext ADR's §12 addendum)
without a redesign, while today every real Set only ever has one
product_id value across its rows (the single-product generation scope
Phase 6.3/Phase 8 already established, unchanged by this).

role is snapshotted from the image's role at selection time, not
re-read from ProductReferenceImage live - the image's own role could
theoretically be re-classified later by a subsequent Reference Scoring
run; this row records what it was told at the time of selection.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class GenerationReferenceSetImage(Base):
    __tablename__ = "generation_reference_set_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    generation_reference_set_id: Mapped[str] = mapped_column(
        ForeignKey("generation_reference_sets.id"), nullable=False
    )
    product_reference_image_id: Mapped[str] = mapped_column(
        ForeignKey("product_reference_images.id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
