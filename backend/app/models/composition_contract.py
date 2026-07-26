"""
Composition Contract artifact (ADR 0001 §9, Package B).

Slide-scoped and versioned like every other analysis artifact, so a contract
can be superseded by re-analysis while historical ones stay inspectable.
Editable later; this package deliberately ships no editing UI.
"""

from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CompositionContractArtifact(Base, AnalysisArtifactMixin):
    __tablename__ = "composition_contracts"

    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False, index=True)
    device: Mapped[str | None] = mapped_column(String(48), nullable=True)
    device_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    contract_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_composition_contracts_slide_current", "slide_id", "is_current"),
    )
