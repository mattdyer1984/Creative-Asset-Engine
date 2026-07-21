"""
Creative — the central entity of the data model (plan §6).

One persisted MarketingCreative = one row here. project_id is nullable:
a Creative can be imported, analysed, and reach a full Creative Blueprint
without ever being assigned to a Project (guiding principle 1 — see
implementation plan §1).

product_id is a real foreign key as of M3 (Product management) - nullable
until the user assigns this creative to a new or existing Product.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._shared import new_uuid, utcnow


class Creative(Base):
    __tablename__ = "creatives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # Optional organisational grouping - not required (plan §1, §6).
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )

    # Nullable until the user assigns this creative to a Product (M3).
    product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id"), nullable=True
    )

    stored_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # Provenance from the Import Provider that produced this creative
    # (plan §5) - never used by the analysis pipeline, only surfaced to
    # the user via the Creative Blueprint's source references.
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(2048), nullable=False)
    raw_metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    imported_at: Mapped[datetime] = mapped_column(default=utcnow)

    blueprint: Mapped["CreativeBlueprint"] = relationship(
        back_populates="creative", uselist=False, cascade="all, delete-orphan"
    )
    product: Mapped["Product | None"] = relationship()
