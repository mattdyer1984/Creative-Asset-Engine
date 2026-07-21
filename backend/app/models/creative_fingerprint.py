"""
CreativeFingerprint — the Analysis Artifact produced by the Creative
Fingerprint Stage (plan §6.3, §6.5, §9).

Owned by Creative. is_current is scoped to creative_id: at most one
CreativeFingerprint per creative has is_current=True at any time.
"""

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CreativeFingerprint(Base, AnalysisArtifactMixin):
    __tablename__ = "creative_fingerprints"

    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"), nullable=False)
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
