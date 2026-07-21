"""
RecreationPrompt — the Analysis Artifact produced by the Recreation
Prompt Stage (plan §6.3, §6.5, §10).

Owned by Creative. is_current is scoped to creative_id. Unlike the other
Creative-scoped artifacts, this one explicitly records which
ProductLockProfile and CreativeFingerprint VERSIONS it was composed from
(plan §7's key design point) - a RecreationPrompt is meaningless without
knowing exactly which upstream versions produced it.
"""

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class RecreationPrompt(Base, AnalysisArtifactMixin):
    __tablename__ = "recreation_prompts"

    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"), nullable=False)
    product_lock_profile_id: Mapped[str] = mapped_column(
        ForeignKey("product_lock_profiles.id"), nullable=False
    )
    creative_fingerprint_id: Mapped[str] = mapped_column(
        ForeignKey("creative_fingerprints.id"), nullable=False
    )
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
