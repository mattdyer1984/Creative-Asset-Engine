"""
ProductBundle — Phase 5.8 of the catalogue layer (see MIGRATION_PLAN.md's
frozen catalogue ADR). Declares that N Products are sold together as one
sellable unit. Pure composition, not a Product subtype and not itself a
Product Profile subject - a bundle has no shape/color/dimensions of its
own to describe (Product's vocabulary is deliberately single-valued per
physical object, which a multi-item bundle can't honestly satisfy - see
the ADR's Bundle philosophy section). Its "profile" is always assembled
at read time from its members' real, unmodified ProductProfiles
(app.services.product_profile.assemble_product_profile, called once per
member - Phase 5.11's job), never a new merge/vocabulary of its own.

Also deliberately carries no commercial data (price/seller/etc.) - that
belongs on whichever Listing(s) sell this bundle, not the bundle itself,
since in principle the same bundle could be found re-listed elsewhere
under a second Listing with a different price.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class ProductBundle(Base):
    __tablename__ = "product_bundles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
