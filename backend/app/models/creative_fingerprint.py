"""
CreativeFingerprint — the Analysis Artifact produced by the Creative
Fingerprint Stage (plan §6.3, §6.5, §9).

Owned by Creative (legacy) / Slide (Phase 2+). is_current is scoped
accordingly: at most one CreativeFingerprint per creative/slide has
is_current=True at any time.

Transitional (Phase 2.3 of the Slideshow/Slide migration) - see
OCRResult's docstring for the creative_id/slide_id coexistence pattern,
identical here.
"""

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CreativeFingerprint(Base, AnalysisArtifactMixin):
    __tablename__ = "creative_fingerprints"

    creative_id: Mapped[str | None] = mapped_column(ForeignKey("creatives.id"), nullable=True)
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id"), nullable=True)
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False)
