"""
Analysis Artifact mixin (plan §6.5).

Every stage's output (OCRResult, ProductReferenceImage, ProductLockProfile,
CreativeFingerprint, MarketingAnalysis, RecreationPrompt) shares the same
four columns. This mixin exists purely to avoid retyping them six times -
it is NOT a new architectural layer, just a DRY convenience the plan
explicitly called for.

is_current is scoped to whatever entity naturally owns that artifact type
(creative_id for five of the six artifacts, product_id for
ProductReferenceImage) - the mixin doesn't (and can't) enforce that
scoping itself, since it varies per artifact; each model's own queries
are responsible for filtering is_current within the correct scope.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._shared import new_uuid, utcnow


class AnalysisArtifactMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
