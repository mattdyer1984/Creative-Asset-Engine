"""
ProductBundleMember — Phase 5.8 of the catalogue layer (see
MIGRATION_PLAN.md's frozen catalogue ADR). Join table: which Products,
and how many of each, compose a ProductBundle. Deliberately carries
nothing beyond the relationship + quantity - no attribute data of its
own, since that's the member Product's own Profile's job, not this
table's.

quantity supports the "multipack" case for free (Phase 5.8's naming
discussion): a multipack is just a ProductBundle with one distinct
member and quantity > 1, not a separate entity type.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class ProductBundleMember(Base):
    __tablename__ = "product_bundle_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    bundle_id: Mapped[str] = mapped_column(ForeignKey("product_bundles.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
