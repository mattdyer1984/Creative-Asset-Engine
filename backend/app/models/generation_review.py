"""
GenerationReview — Phase 12 (Human Feedback & Learning System, see
MIGRATION_PLAN.md). Permanently records the human reviewer's (Matt's)
verdict on one GenerationLog - a 1:1 row (generation_log_id unique),
created via POST .../generation-logs/{id}/review, the only write path
into this table. This is a labelled training example, not a UI
convenience: overall_score/main_issue/comment are the human-provided
ground truth a future personalised quality model would train against,
so nothing here is ever silently defaulted or inferred - the endpoint
that creates a row requires overall_score and main_issue explicitly
(there is no scenario where this table holds a partial/guessed review).

learning_mode_enabled snapshots AppSetting.learning_mode_enabled at
review time, per the spec's own review.json shape - so a later query
over historical reviews can tell whether a given review was collected
under mandatory-review conditions or not, even after the global setting
is later flipped off.

main_issue is an open string (not a DB-level enum), validated against
the closed set from the spec in the router - same "open column, closed
set enforced at the API layer" pattern as
ProductReferenceImage.library_status/VALID_LIBRARY_STATUSES.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class GenerationReview(Base):
    __tablename__ = "generation_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    generation_log_id: Mapped[str] = mapped_column(
        ForeignKey("generation_logs.id"), nullable=False, unique=True
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    main_issue: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    learning_mode_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
