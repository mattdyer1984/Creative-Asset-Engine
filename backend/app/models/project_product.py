"""
ProjectProduct — Phase 10.5 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §3, Project role
reversal). Join table: which Products a Project's work currently
involves. Mirrors app.models.product_bundle_member.ProductBundleMember's
exact minimal shape - a pure membership reference, no attribute data of
its own.

Product (and its Canonical Reference Library) deliberately does NOT move
into Project's ownership even after this reversal - a Product is durable,
cross-Project-reusable knowledge (see app.models.product's own
docstring), while a Project is a scoped unit of creative work that may
reference many Products, and the same Product may be referenced by many
Projects over time. This table is that reference, not a re-parenting.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class ProjectProduct(Base):
    __tablename__ = "project_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
