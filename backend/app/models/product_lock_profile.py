"""
ProductLockProfile — the Analysis Artifact produced by the Product Lock
Profile Stage (plan §6.3, §6.5, §7, §8).

Owned by Product. is_current is scoped to product_id: at most one
ProductLockProfile per product has is_current=True at any time.

reference_image_ids_json is a SNAPSHOT of which ProductReferenceImage
ids were current at generation time - not a live join. This means an old
profile version always shows exactly the images it was built from, even
if a later Product Isolation run has since produced new ones (plan §7's
key design point on this).
"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class ProductLockProfile(Base, AnalysisArtifactMixin):
    __tablename__ = "product_lock_profiles"

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    structured_json: Mapped[str] = mapped_column(Text, nullable=False)
    reference_image_ids_json: Mapped[str] = mapped_column(Text, default="[]")
