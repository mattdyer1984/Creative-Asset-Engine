"""
Persisted text ownership (ADR 0001, Package A).

Ownership was a runtime result: computed, used, discarded. That made it
impossible to answer "who owned this block when this image was produced?"
after the fact, which is exactly the question a manifest needs to stay
honest once a project is re-analysed.

Promoted to a slide-scoped analysis artifact using the existing lifecycle
conventions, so provenance, versioning and staleness behave as they do for
every other artifact.

**User decisions stay owned by the Creative Project Profile.** This artifact
records the EFFECTIVE decisions that were in force for one run - a snapshot
of what was applied, not a second place where policy lives. Two homes for
the same decision is how they drift apart.
"""

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class TextOwnershipArtifact(Base, AnalysisArtifactMixin):
    __tablename__ = "text_ownership_artifacts"

    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False, index=True)

    #: The profile whose effective policies were applied. Pinned, not resolved
    #: at read time - re-analysis must not rewrite the explanation of a past run.
    project_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    #: Which composition contract informed the spatial decisions (Package C),
    #: and the schema it was written under. The version is stamped rather than
    #: joined: a contract can be superseded, and a past run must stay readable
    #: in its own terms without chasing a row that has since moved on.
    composition_contract_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    composition_contract_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    #: Bumped when routing logic would produce different owners for identical
    #: input, so a change in decisions is attributable.
    ownership_model_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")

    blocks_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    #: Phase F. Whether anything CHECKED this artifact, kept separate from
    #: confidence - a model can be certain and wrong, and a deterministic
    #: rule can be right with no confidence at all.
    validation_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    validation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_text_ownership_artifacts_slide_current", "slide_id", "is_current"),
    )
