"""
GenerationAttempt — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §12). The grouping
entity for one candidate-count-aware call into the Generation Engine:
N `GeneratedImage` rows belong to one GenerationAttempt, exactly
mirroring how N `GenerationReferenceSetImage` rows already belong to
one `GenerationReferenceSet` (Product Lock v2 §3).

Additive, not a modification of GeneratedImage - a pre-Phase-10.2
GeneratedImage genuinely has no attempt (see that model's own
generation_attempt_id docstring).

decision_json is the GenerationPlan (app.services.decision_engine) that
produced this attempt, persisted verbatim - same "record the attempt,
including how it was made" discipline GeneratedImage's own
provider/model_name/prompt_used columns already establish.

retry_of_generation_attempt_id (nullable self-FK) chains the retry
loop (§14) - null for a first attempt, pointing at the prior attempt
for every subsequent one. Phase 10.2 is explicitly the *basic* retry
loop per the vNext ADR's own phased-implementation note (§19 item 3,
"proves Autonomous Quality end-to-end... before Creative/Photorealism/
Text Quality exist") - a retry here means "generate another full
attempt with the same GenerationPlan," not yet the fully adaptive
"read *why* the previous attempt failed and change strategy" behavior
§11 describes, since the quality signals that adaptive routing would
read (photorealism_json, creative_fidelity_json) don't exist until
later sub-phases.

bundle_composition_id (Phase 10.7, §12's "Bundle Composition" addendum)
is mutually exclusive with generation_reference_set_id above - set
only when this attempt used Bundle Composition (several distinct
products composed into one scene), in which case
generation_reference_set_id stays null (a bundle attempt has N Sets,
one per member, not one - see BundleCompositionMember, not this row).
"""

from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class GenerationAttempt(Base):
    __tablename__ = "generation_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False)
    creative_specification_id: Mapped[str] = mapped_column(
        ForeignKey("creative_specifications.id"), nullable=False
    )
    generation_reference_set_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_reference_sets.id"), nullable=True
    )
    bundle_composition_id: Mapped[str | None] = mapped_column(
        ForeignKey("bundle_compositions.id"), nullable=True
    )
    quality_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    retry_of_generation_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("generation_attempts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
