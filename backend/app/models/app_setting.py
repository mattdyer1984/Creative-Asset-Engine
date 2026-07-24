"""
AppSetting — Phase 12 (Human Feedback & Learning System, see
MIGRATION_PLAN.md). A single, permanent singleton row (id fixed to
SINGLETON_ID) holding global application settings - today just
learning_mode_enabled. Not a generic key-value store: this codebase's
own convention (see e.g. ProductReferenceImage.library_status's own
"real, closed set" reasoning) is concrete typed columns over speculative
generality, and exactly one setting is asked for right now.

learning_mode_enabled gates whether a human review is mandatory before
a Generation Results Modal can be closed (see GenerationReview) - "the
foreseeable future" per the spec, with an explicit design requirement
that turning it off later must not require any architecture change,
only reading this one flag differently at the call sites that already
check it.
"""

from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import utcnow

SINGLETON_ID = "singleton"


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: SINGLETON_ID)
    learning_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
