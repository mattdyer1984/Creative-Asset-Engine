"""
Creative Project Profile (ADR 0001 §14, WP-1.1).

The one durable, slideshow-scoped source of truth for how a creative project
should be recreated. Introduced minimal - text mode, copy and overlay policy,
production value, typography system - and extended in place by later work
packages. No temporary table is created to be retired.

**Scoped to the slideshow, not to `projects.id`.** A "creative project" in
the ADR sense is one coherent set of slides sharing a design system, a cast
and a typographic voice. The existing `projects` table is a coarser
container: in the development database a single project holds 41 unrelated
slideshows, so scoping here would make one profile claim to describe all of
them.

**Analysis and human decisions live in separate columns.** `analysed_*` is
what the analyser inferred and is overwritten on every re-analysis;
`user_*` is what a person decided and must survive it. Merging them into one
JSON document would make that guarantee unenforceable - the whole point is
that re-running analysis can never silently discard a user's choice.

Uses AnalysisArtifactMixin exactly as the six existing artifact types do, so
provenance (`analysis_run_id`), versioning (`schema_version`) and staleness
(`is_current`) behave the way every other artifact in this codebase does.
"""

from sqlalchemy import JSON, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class CreativeProjectProfile(Base, AnalysisArtifactMixin):
    __tablename__ = "creative_project_profiles"

    slideshow_id: Mapped[str] = mapped_column(
        ForeignKey("slideshows.id"), nullable=False, index=True
    )

    # --- what the analyser inferred -------------------------------------
    # Nullable because a profile may exist before every stage has run, and
    # because an honest "not determined" is better than a default that reads
    # as a finding.
    analysed_primary_text_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    analysed_text_mode_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysed_typography_system_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    classification_evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- what a human decided -------------------------------------------
    # Never written by the analyser. Null means "no human has expressed an
    # opinion", which is distinct from "the human agreed with the analyser".
    user_primary_text_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_copy_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_overlay_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_production_value_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_typography_overrides_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        # The hot query is "the current profile for this slideshow".
        Index(
            "ix_creative_project_profiles_slideshow_current",
            "slideshow_id",
            "is_current",
        ),
    )
