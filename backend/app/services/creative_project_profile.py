"""
Creative Project Profile persistence (ADR 0001 §14, WP-1.1).

**The guarantee this module exists to provide:** re-running analysis never
discards a human decision. The analyser writes `analysed_*`; a person writes
`user_*`; `record_analysis` carries the latter forward untouched. A user who
set the overlay policy to `remove` must not find it silently restored to
`keep` because the slideshow was analysed again.

Versioning follows the codebase's existing artifact convention: a new row per
analysis, the previous row marked `is_current=False`, provenance through
`analysis_run_id`. Nothing is updated in place, so the history of what was
inferred - and what a human corrected - stays auditable.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.creative_project_profile import CreativeProjectProfile
from app.services.profile_schema import (
    SCHEMA_VERSION,
    ClassificationEvidence,
    CopyPolicy,
    OverlayPolicy,
    ProductionValueStrategy,
    TextMode,
    TypographySystem,
    UserTypographyOverrides,
    merge_typography,
)

logger = logging.getLogger(__name__)

#: ADR §13. Suggested, visible, and overridable - never silent.
DEFAULT_COPY_POLICY = CopyPolicy.PRESERVE_VERBATIM
DEFAULT_OVERLAY_POLICY = OverlayPolicy.KEEP
DEFAULT_PRODUCTION_VALUE = ProductionValueStrategy.REFINE


class ProfileSchemaMismatch(RuntimeError):
    """
    A persisted profile was written by an incompatible schema version.

    Raised rather than coerced: silently reading an old shape as if it were
    the current one is how a field quietly means something different from
    what its writer intended.
    """


def get_current_profile(db: Session, slideshow_id: str) -> CreativeProjectProfile | None:
    return db.scalars(
        select(CreativeProjectProfile).where(
            CreativeProjectProfile.slideshow_id == slideshow_id,
            CreativeProjectProfile.is_current.is_(True),
        )
    ).first()


def record_analysis(
    db: Session,
    *,
    slideshow_id: str,
    analysis_run_id: str,
    primary_text_mode: TextMode | None = None,
    text_mode_confidence: float | None = None,
    typography_system: TypographySystem | None = None,
    classification_evidence: ClassificationEvidence | None = None,
) -> CreativeProjectProfile:
    """
    Record a fresh analysis, carrying every existing user decision forward.

    Supersedes the previous current row rather than updating it, so the
    history of what was inferred stays intact and a regression in the
    analyser is visible rather than overwritten.
    """
    previous = get_current_profile(db, slideshow_id)

    profile = CreativeProjectProfile(
        slideshow_id=slideshow_id,
        analysis_run_id=analysis_run_id,
        schema_version=SCHEMA_VERSION,
        is_current=True,
        analysed_primary_text_mode=str(primary_text_mode) if primary_text_mode else None,
        analysed_text_mode_confidence=text_mode_confidence,
        analysed_typography_system_json=(
            typography_system.model_dump(mode="json") if typography_system else None
        ),
        classification_evidence_json=(
            classification_evidence.model_dump(mode="json") if classification_evidence else None
        ),
    )

    if previous is not None:
        # The whole point of the analysed/user split. These are NOT copied
        # from the analyser's output - they are the human's, and re-analysis
        # has no authority over them.
        profile.user_primary_text_mode = previous.user_primary_text_mode
        profile.user_copy_policy = previous.user_copy_policy
        profile.user_overlay_policy = previous.user_overlay_policy
        profile.user_production_value_strategy = previous.user_production_value_strategy
        profile.user_typography_overrides_json = previous.user_typography_overrides_json
        previous.is_current = False

    db.add(profile)
    db.flush()
    return profile


def apply_user_decisions(
    db: Session,
    profile: CreativeProjectProfile,
    *,
    primary_text_mode: TextMode | None = None,
    copy_policy: CopyPolicy | None = None,
    overlay_policy: OverlayPolicy | None = None,
    production_value_strategy: ProductionValueStrategy | None = None,
    typography_overrides: UserTypographyOverrides | None = None,
) -> CreativeProjectProfile:
    """
    Record explicit human decisions on the current profile.

    Updates in place - unlike analysis, a user decision is not a new
    observation to be versioned, it is the standing instruction. `None`
    means "not specified in this call" and leaves the existing value alone;
    clearing a decision is `reset_user_decisions`.
    """
    if primary_text_mode is not None:
        profile.user_primary_text_mode = str(primary_text_mode)
    if copy_policy is not None:
        profile.user_copy_policy = str(copy_policy)
    if overlay_policy is not None:
        profile.user_overlay_policy = str(overlay_policy)
    if production_value_strategy is not None:
        profile.user_production_value_strategy = str(production_value_strategy)
    if typography_overrides is not None:
        profile.user_typography_overrides_json = typography_overrides.model_dump(mode="json")
    db.flush()
    return profile


def reset_user_decisions(db: Session, profile: CreativeProjectProfile) -> CreativeProjectProfile:
    """
    Explicitly discard human decisions - the only supported way to lose them.

    Deliberately separate from re-analysis so that "start again from what the
    machine thinks" is a decision someone takes, not a side effect.
    """
    profile.user_primary_text_mode = None
    profile.user_copy_policy = None
    profile.user_overlay_policy = None
    profile.user_production_value_strategy = None
    profile.user_typography_overrides_json = None
    db.flush()
    return profile


def _require_supported(document: dict | None, field: str) -> dict | None:
    if document is None:
        return None
    version = document.get("schema_version")
    if version not in (None, SCHEMA_VERSION):
        raise ProfileSchemaMismatch(
            f"{field} was written by schema {version!r}; this build understands "
            f"{SCHEMA_VERSION!r}. Re-run analysis rather than reading it as current."
        )
    return document


def effective_primary_text_mode(profile: CreativeProjectProfile) -> TextMode | None:
    """The user's decision if there is one, otherwise the analyser's."""
    chosen = profile.user_primary_text_mode or profile.analysed_primary_text_mode
    return TextMode(chosen) if chosen else None


def effective_copy_policy(profile: CreativeProjectProfile) -> CopyPolicy:
    return CopyPolicy(profile.user_copy_policy) if profile.user_copy_policy else DEFAULT_COPY_POLICY


def effective_overlay_policy(profile: CreativeProjectProfile) -> OverlayPolicy:
    return (
        OverlayPolicy(profile.user_overlay_policy)
        if profile.user_overlay_policy
        else DEFAULT_OVERLAY_POLICY
    )


def effective_production_value_strategy(profile: CreativeProjectProfile) -> ProductionValueStrategy:
    return (
        ProductionValueStrategy(profile.user_production_value_strategy)
        if profile.user_production_value_strategy
        else DEFAULT_PRODUCTION_VALUE
    )


def effective_typography_system(profile: CreativeProjectProfile) -> TypographySystem | None:
    """
    The analysed system with any human corrections laid over it, per role.

    Returns None when nothing has been analysed - callers must handle the
    absence rather than receive an empty system that looks like a finding.
    """
    analysed_document = _require_supported(
        profile.analysed_typography_system_json, "analysed_typography_system_json"
    )
    if analysed_document is None:
        return None
    analysed = TypographySystem.model_validate(analysed_document)

    override_document = _require_supported(
        profile.user_typography_overrides_json, "user_typography_overrides_json"
    )
    overrides = (
        UserTypographyOverrides.model_validate(override_document) if override_document else None
    )
    return merge_typography(analysed, overrides)
