"""
CreativeBlueprint — the single canonical, user-facing object (plan §1, §6, §10).

Owned 1:1 by Creative. Not itself versioned - it's a live pointer to
whichever version of each sub-analysis is currently "current", plus a
status field driving the Import -> Queue -> Analyse -> Ready/Failed UX.

M1 only ever creates this row and leaves it at status="imported": no
analysis exists yet (that's M2 onward), so all current_*_id fields stay
NULL until then.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._shared import new_uuid, utcnow

# Lifecycle: imported -> queued -> analyzing -> ready
#                          \-> failed        <-/
#
# "queued" exists as its own state (distinct from "analyzing") because
# batch imports mean many creatives can be waiting for analysis at once -
# an explicit queued state lets the UI show "12 waiting, 1 analyzing"
# rather than a single ambiguous "processing" state for all of them.
#
# "ready" and "failed" are alternative terminal outcomes, not sequential
# steps - a Blueprint reaches exactly one of them, never both. Failure
# can occur while queued (e.g. the queue itself errors) or while
# analyzing (e.g. a provider call fails); "imported" itself doesn't yet
# have a failure path since M1 has no analysis logic to fail.
#
# M1 only ever sets STATUS_IMPORTED (import has no queueing/analysis
# logic yet - that arrives with the M2 orchestrator). The other three
# values exist now so the vocabulary is settled before M2 needs it.
STATUS_IMPORTED = "imported"
STATUS_QUEUED = "queued"
STATUS_ANALYZING = "analyzing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


class CreativeBlueprint(Base):
    __tablename__ = "creative_blueprints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    creative_id: Mapped[str] = mapped_column(
        ForeignKey("creatives.id"), nullable=False, unique=True
    )

    status: Mapped[str] = mapped_column(String(32), default=STATUS_IMPORTED)

    # Pointers to the current version of each sub-analysis. All nullable
    # until the corresponding milestone (M2 OCR, M4 Product Lock Profile,
    # M5 Fingerprint/Marketing Analysis, M6 Recreation Prompt) generates one.
    current_ocr_result_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_product_lock_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_creative_fingerprint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_marketing_analysis_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_recreation_prompt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Which stage most recently failed and why (plan §1, §11 M7's "the
    # pipeline is an implementation detail, but 'what broke' still needs a
    # clear answer" requirement). Set/cleared by the Orchestrator in
    # lockstep with status becoming FAILED/READY.
    #
    # This can't be reconstructed after the fact from AnalysisRun history
    # alone: a stage that fails a prerequisite check (e.g. "no product
    # assigned") correctly creates no AnalysisRun at all - nothing was
    # attempted, so there's nothing to record there - which means the
    # *only* place this information can reliably live is here, set at the
    # moment of failure, not derived later from a query that structurally
    # can't see every kind of failure.
    last_failed_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_failed_stage_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Snapshot of the Creative's import provenance, copied in at creation
    # time (plan §6) - kept on the Blueprint itself so the single
    # assembled view never needs to join back to Creative for this.
    source_references_json: Mapped[str] = mapped_column(Text, default="{}")

    # Empty in V1; placeholder for future image-generation outputs.
    future_generated_assets_json: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    creative: Mapped["Creative"] = relationship(back_populates="blueprint")
