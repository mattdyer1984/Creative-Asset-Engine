"""
Quality Engine — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §13).

**Product Fidelity reuses `ImageValidationResult`/Stage 1 Identity
Validation unchanged** (§13's own explicit instruction) - this module
runs the existing `SlideImageValidationStage` (Phase 8.4/9.4) exactly
as the standalone `POST .../validate` endpoint already does, then
wraps its result in a `QualityAssessment` row rather than duplicating
any of its logic or fields.

`creative_fidelity_json`/`photorealism_json`/`text_quality_json` are
never populated by this sub-phase - those dimensions don't exist yet
(Phases 10.3/10.4/the eventual Text Intelligence phase). `accepted`/
`overall_confidence_score` are computed purely from
`image_validation_result.passed` for now: 1.0/True if it passed,
0.0/False if not. This is a deliberately honest, single-input
computation, not the full multi-dimension weighting §13 eventually
describes - weighting scores that don't exist yet would be fabricating
a signal, not computing one. Both are still computed in code, never
asked of the AI as a bare boolean, matching this codebase's standing
rule; there is just only one real input so far.
"""

from sqlalchemy.orm import Session

from app.models.generated_image import GeneratedImage
from app.models.image_validation_result import ImageValidationResult
from app.models.quality_assessment import QualityAssessment
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.image_validation_stage import SlideImageValidationStage


def assess_candidate(db: Session, generated_image: GeneratedImage) -> QualityAssessment | StageResult:
    """
    Runs Stage 1 Identity Validation + Stage 2 creative validation
    (unchanged, Phase 8.4/9.4) against this specific candidate, then
    computes and persists this sub-phase's `QualityAssessment`. Returns
    a `StageResult` (never raises) on the rare case validation itself
    can't run (e.g. no immutable Product Profile fields yet) - the same
    "clean, explained failure" shape `run_generation_attempt` already
    returns, so a caller checking one type covers both engines.
    """
    stage_result = SlideImageValidationStage().run(db, generated_image)
    if not stage_result.succeeded:
        return stage_result

    image_validation_result = (
        db.query(ImageValidationResult)
        .filter(
            ImageValidationResult.generated_image_id == generated_image.id,
            ImageValidationResult.is_current.is_(True),
        )
        .one()
    )

    assessment = QualityAssessment(
        generated_image_id=generated_image.id,
        image_validation_result_id=image_validation_result.id,
        overall_confidence_score=1.0 if image_validation_result.passed else 0.0,
        accepted=image_validation_result.passed,
    )
    db.add(assessment)
    # A real commit, not just a flush - unlike every other write in this
    # module's call chain, nothing runs afterward to piggyback a commit
    # on (SlideImageValidationStage's own mark_succeeded/mark_failed
    # already committed its own row before this point). Without this,
    # get_db()'s session.close() rolls the assessment back - a real bug
    # found via live verification, not a style preference.
    db.commit()
    return assessment
