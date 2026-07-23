"""
QualityAssessment — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §13). One per
`GeneratedImage` candidate - the Quality Engine's verdict on that
specific candidate, closing the Decision -> Generation -> Quality loop
(§14) with a real, computed accept/reject signal.

**Product Fidelity reuses ImageValidationResult/Stage 1 Identity
Validation unchanged** (§13's own explicit instruction) -
image_validation_result_id references it rather than duplicating any
of its fields; this table adds the *other* quality dimensions on top.

creative_fidelity_json / photorealism_json / text_quality_json are all
nullable and genuinely unused as of Phase 10.2 - those dimensions are
later, separate sub-phases (10.3 Photorealism, 10.4 Creative
Intelligence, the eventual Text Intelligence phase). Adding this
table's full shape now (rather than only the columns 10.2 populates)
follows this engagement's own expand-as-you-go migration discipline:
each later phase fills in one more nullable column, an additive change,
instead of reopening this table's schema every time.

overall_confidence_score / accepted (Phase 10.2): computed purely from
`image_validation_result.passed` for now (1.0/accepted if it passed,
0.0/rejected if not) - the ADR's full weighting across every dimension
(§13) only makes sense once photorealism/creative-fidelity scores
actually exist to weigh; scoring based on dimensions that don't exist
yet would be fabricating a signal, not computing one. Both are still
computed in code, never asked of the AI as a bare boolean, matching
`image_validation_stage.py`'s own standing rule - there's just only one
real input to that computation so far.

image_validation_result_id / image_validation_result_ids_json (the
latter added Phase 10.7, §12's "Bundle Composition" addendum) are
mutually exclusive, the same pattern GenerationAttempt's own
generation_reference_set_id/bundle_composition_id pair uses: a
single-product candidate gets exactly one ImageValidationResult
(image_validation_result_id, unchanged); a Bundle Composition candidate
gets one ImageValidationResult per member product - "every product in
the scene must still retain its own canonical identity, reference set
and validation," per the user's own explicit instruction - stored as a
plain JSON list of ids rather than a new join table, since nothing
needs to query this list independently of its owning QualityAssessment
row. image_validation_result_id relaxes to nullable in the same
migration that adds this column, for a bundle candidate genuinely has
no single result to point at.
"""

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class QualityAssessment(Base):
    __tablename__ = "quality_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    generated_image_id: Mapped[str] = mapped_column(ForeignKey("generated_images.id"), nullable=False)
    image_validation_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("image_validation_results.id"), nullable=True
    )
    image_validation_result_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    creative_fidelity_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    photorealism_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    text_quality_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overall_confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
