"""
Product — canonical, reusable across creatives (plan §1, §7).

Not owned by Creative or Project - a Creative optionally points at a
Product (creative.product_id), and a Product optionally belongs to a
Project (for grouping), but neither owns the other. This is what lets
the same Product be the target of many Creatives over time, which is
the whole point of the Product Lock Profile being reusable (plan
guiding principle 5).
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
