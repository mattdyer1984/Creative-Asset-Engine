"""
ProductAppearance — join between a Slide and a Product (Phase 2 of the
Slideshow/Slide migration). Replaces Creative.product_id's single,
direct FK: a slide can show zero, one, or several products, and the
same product can recur across slides - genuinely many-to-many, unlike
the old one-Creative-one-Product assumption.

bbox fields are nullable: a ProductAppearance created by manual/backfilled
assignment (no detection ever ran) has no real bounding box, only a
prominence/confidence pair - see the Phase 2.2 backfill, which creates
one ProductAppearance per Creative.product_id with prominence="primary",
confidence=1.0, and a null bbox, since it records a fact the user
asserted, not one Product Isolation detected.

Additive as of Phase 2.1 - nothing reads or writes this table yet.
"""

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._shared import new_uuid, utcnow


class ProductAppearance(Base):
    __tablename__ = "product_appearances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)

    # Fractional coordinates (0.0-1.0), same convention as the Product
    # Isolation provider's bounding boxes (app.ai_providers.openai_adapter's
    # PRODUCT_ISOLATION_RESPONSE_SCHEMA) - null when this appearance was
    # asserted rather than detected (see module docstring).
    x_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    x_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    prominence: Mapped[str] = mapped_column(String(32), default="primary")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    slide: Mapped["Slide"] = relationship(back_populates="product_appearances")
    product: Mapped["Product"] = relationship()
