"""
Quality Engine — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §13); Photorealism
dimension added in Phase 10.3.

**Product Fidelity reuses `ImageValidationResult`/Stage 1 Identity
Validation unchanged** (§13's own explicit instruction) - this module
runs the existing `SlideImageValidationStage` (Phase 8.4/9.4) exactly
as the standalone `POST .../validate` endpoint already does, then
wraps its result in a `QualityAssessment` row rather than duplicating
any of its logic or fields. It remains a hard *floor*: if it fails, no
Photorealism call is spent at all (same short-circuit-to-save-real-cost
discipline Stage 1/Stage 2 already use inside SlideImageValidationStage
itself) and `accepted=False`/`overall_confidence_score=0.0` - a real
identity/creative failure is disqualifying regardless of how
photorealistic the (wrong) image looks.

Photorealism (§13, Phase 10.3) is the graded dimension once that floor
clears - the full checklist from the request (lighting, shadows,
material accuracy, reflections, texture, perspective, object
integrity, human anatomy, AI-artefact detection, sharpness), evaluated
by one `VisionAnalysisProvider.analyze_creative` call against the
candidate image alone (no reference images, no Product Profile - this
is a self-contained visual-quality judgment, unlike Product Fidelity's
comparison-based checks). `PHOTOREALISM_FLOOR`/scoring are computed in
code from the structured per-field judgments, never asked of the AI as
a bare score, matching this codebase's standing rule everywhere else a
pass/fail or score is derived from AI-provided facts.

`creative_fidelity_json`/`text_quality_json` are still never populated
by this sub-phase - those remain later, separate sub-phases (10.4/the
eventual Text Intelligence phase).

**Bundle Composition (Phase 10.7, §12's addendum)**: `assess_bundle_candidate`
is a parallel entry point for a candidate produced by
`run_bundle_generation_attempt` - "every product in the scene must
still retain its own canonical identity, reference set and validation,"
per the user's own explicit instruction, so Product Fidelity becomes N
independent Stage-1-only validations (one per member,
`run_bundle_member_identity_validation`) rather than one. `accepted`
requires **every** member to individually pass - never an averaged or
majority score, since one wrong product in a bundle shot is a real
failure, not a partial one. Photorealism still runs once per candidate
image (a single image has one photorealism judgment regardless of how
many products are in it), spent only once every member's identity
check clears - the same floor-before-spend discipline as the single-
product path, generalized from "the one product passed" to "every
member passed."

**Story Slide feature (see MIGRATION_PLAN.md)**: `assess_story_candidate`
is a third parallel entry point, for a candidate produced by
`run_story_generation_attempt` (no product at all). There is no Stage 1
Identity or Stage 2 per-field fidelity to check - no product, no
Product Profile, no reference set - so acceptance is decided by
Photorealism alone, the same dimension already layered on top of Stage
2 in the product path. No floor-before-spend short-circuit is needed
here since there is no earlier, cheaper stage to short-circuit past.
"""

import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.bundle_composition import BundleCompositionMember
from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.models.image_validation_result import ImageValidationResult
from app.models.quality_assessment import QualityAssessment
from app.services.provider_call_log import record_provider_call
from app.slideshow_stages.base import StageResult
from app.prompts import validation as _validation_prompts
from app.slideshow_stages.image_validation_stage import (
    SlideImageValidationStage,
    run_bundle_member_identity_validation,
)

PHOTOREALISM_SCHEMA = {
    "type": "object",
    "properties": {
        "realistic_lighting": {"type": "boolean"},
        "believable_shadows": {"type": "boolean"},
        "material_accuracy": {"type": "boolean"},
        "reflections_correct": {"type": "boolean"},
        "texture_quality": {"type": "string", "enum": ["poor", "fair", "good", "excellent"]},
        "perspective_correct": {"type": "boolean"},
        "object_integrity": {"type": "boolean"},
        # A tri-state, not a boolean: most product-ad images have no
        # humans in them at all, and forcing an AI to judge "correct/
        # incorrect" anatomy that isn't present would fabricate a
        # signal - "not_applicable" is a real, distinct answer, not a
        # default to guess between the other two.
        "human_anatomy": {"type": "string", "enum": ["correct", "incorrect", "not_applicable"]},
        "ai_artefacts_detected": {"type": "boolean"},
        "image_sharpness": {"type": "string", "enum": ["poor", "fair", "good", "excellent"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "realistic_lighting", "believable_shadows", "material_accuracy",
        "reflections_correct", "texture_quality", "perspective_correct",
        "object_integrity", "human_anatomy", "ai_artefacts_detected",
        "image_sharpness", "reasons",
    ],
    "additionalProperties": False,
}

_QUALITY_TIER_SCORE = {"poor": 0.0, "fair": 0.33, "good": 0.67, "excellent": 1.0}

# Photorealism is weighted heavily in `accepted`, per §13's explicit
# instruction ("this dimension is weighted heavily... not treated as a
# soft/optional signal") - a floor comparable to Reference Scoring's
# own QUALITY_FLOOR, not a token pass-most-things gate.
PHOTOREALISM_FLOOR = 0.6


def _build_photorealism_prompt() -> str:
    return _validation_prompts.PHOTOREALISM.render()


# Which validator prompt applies to which rendering family. The scoring
# function and the floor are shared and UNCHANGED - only the criteria
# differ, because "is this well-made?" is the same question in every
# medium while "is this a photograph?" is not.
def _style_validator_for(family):
    from app.services.source_style import RenderingFamily

    return {
        RenderingFamily.PHOTOGRAPHIC: _validation_prompts.PHOTOREALISM,
        RenderingFamily.ILLUSTRATED: _validation_prompts.STYLE_ILLUSTRATED,
        RenderingFamily.RENDER: _validation_prompts.STYLE_RENDER,
        RenderingFamily.MIXED: _validation_prompts.STYLE_MIXED,
    }.get(family, _validation_prompts.PHOTOREALISM)


def _classify_generated_image_style(db: Session, generated_image: GeneratedImage):
    """The source style of the slide this candidate was generated for."""
    from app.models.creative_fingerprint import CreativeFingerprint
    from app.models.scene_analysis import SceneAnalysis
    from app.models.slide import Slide
    from app.services.source_style import classify_source_style

    slide = db.get(Slide, generated_image.slide_id)
    if slide is None:
        return classify_source_style(None)
    fingerprint = (
        db.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
        if slide.current_creative_fingerprint_id
        else None
    )
    scene = (
        db.get(SceneAnalysis, slide.current_scene_analysis_id)
        if slide.current_scene_analysis_id
        else None
    )
    return classify_source_style(
        fingerprint.structured_json if fingerprint else None,
        scene.regions_json if scene else None,
    )


def _score_photorealism(result: dict) -> float:
    boolean_checks = [
        result["realistic_lighting"],
        result["believable_shadows"],
        result["material_accuracy"],
        result["reflections_correct"],
        result["perspective_correct"],
        result["object_integrity"],
        not result["ai_artefacts_detected"],
        result["human_anatomy"] != "incorrect",
    ]
    boolean_fraction = sum(1 for check in boolean_checks if check) / len(boolean_checks)
    texture_component = _QUALITY_TIER_SCORE[result["texture_quality"]]
    sharpness_component = _QUALITY_TIER_SCORE[result["image_sharpness"]]
    return (boolean_fraction * 0.6) + (texture_component * 0.2) + (sharpness_component * 0.2)


def _run_photorealism(db: Session, generated_image: GeneratedImage) -> dict:
    """
    One instrumented Photorealism call (Phase 1 remediation, WP-2).

    Extracted because all three assess_* paths made this identical call
    inline, and none of them recorded it - photorealism scoring was one
    of four modules whose real paid calls were entirely invisible to
    cost and timing reporting. Recording it once here means adding a
    fourth assess_* path cannot silently reintroduce that blind spot.
    """
    vision_provider = default_registry.vision()
    generated_image_bytes = Path(generated_image.file_path).read_bytes()
    usage: dict = {}

    # Judge the candidate in the medium its SOURCE used. Applying the
    # photographic criteria universally is what failed illustrated
    # candidates for being illustrated.
    classification = _classify_generated_image_style(db, generated_image)
    validator_prompt = (
        _style_validator_for(classification.family)
        if classification.is_confident
        else _validation_prompts.PHOTOREALISM
    )

    start = time.perf_counter()
    photorealism_json = vision_provider.analyze_creative(
        image_bytes=generated_image_bytes,
        prompt_spec={"prompt": validator_prompt.render(), "schema_name": "photorealism"},
        response_schema=PHOTOREALISM_SCHEMA,
        usage_sink=usage,
    )
    provider_latency_ms = (time.perf_counter() - start) * 1000

    record_provider_call(
        db,
        provider=vision_provider.provider,
        model=vision_provider.model,
        capability="vision_analysis",
        prompt=validator_prompt,
        usage=usage,
        provider_latency_ms=provider_latency_ms,
        generated_image_id=generated_image.id,
        slide_id=generated_image.slide_id,
        slideshow_id=generated_image.slideshow_id,
    )
    return photorealism_json


def assess_candidate(db: Session, generated_image: GeneratedImage) -> QualityAssessment | StageResult:
    """
    Runs Stage 1 Identity Validation + Stage 2 creative validation
    (unchanged, Phase 8.4/9.4) against this specific candidate first -
    a hard floor. Only once that passes does this spend a second, real
    vision call judging Photorealism (Phase 10.3); a floor failure
    never reaches that call at all, saving the cost on a candidate
    already disqualified for a different reason. Returns a
    `StageResult` (never raises) on the rare case validation itself
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

    photorealism_json: dict | None = None
    if image_validation_result.passed:
        photorealism_json = _run_photorealism(db, generated_image)
        photorealism_score = _score_photorealism(photorealism_json)
        accepted = photorealism_score >= PHOTOREALISM_FLOOR
        overall_confidence_score = photorealism_score
    else:
        accepted = False
        overall_confidence_score = 0.0

    assessment = QualityAssessment(
        generated_image_id=generated_image.id,
        image_validation_result_id=image_validation_result.id,
        photorealism_json=photorealism_json,
        overall_confidence_score=overall_confidence_score,
        accepted=accepted,
    )
    db.add(assessment)
    # A real commit, not just a flush - unlike every other write in this
    # module's call chain, nothing runs afterward to piggyback a commit
    # on (SlideImageValidationStage's own mark_succeeded/mark_failed
    # already committed its own row before this point). Without this,
    # get_db()'s session.close() rolls the assessment back - a real bug
    # found via live verification in Phase 10.2, not a style preference.
    db.commit()
    return assessment


def assess_story_candidate(db: Session, generated_image: GeneratedImage) -> QualityAssessment:
    """
    Story Slide counterpart to assess_candidate (see MIGRATION_PLAN.md) -
    see this module's own docstring for why acceptance is Photorealism
    alone here. Unlike assess_candidate/assess_bundle_candidate, this
    never returns a StageResult - there is no validation prerequisite
    (no Product Profile, no reference set) that could legitimately be
    missing, so there's nothing to short-circuit.
    """
    photorealism_json = _run_photorealism(db, generated_image)
    photorealism_score = _score_photorealism(photorealism_json)
    accepted = photorealism_score >= PHOTOREALISM_FLOOR

    assessment = QualityAssessment(
        generated_image_id=generated_image.id,
        image_validation_result_id=None,
        photorealism_json=photorealism_json,
        overall_confidence_score=photorealism_score,
        accepted=accepted,
    )
    db.add(assessment)
    # Same real-commit reasoning as assess_candidate/assess_bundle_candidate -
    # nothing after this point to piggyback a commit on.
    db.commit()
    return assessment


def assess_bundle_candidate(db: Session, generated_image: GeneratedImage) -> QualityAssessment | StageResult:
    """
    Bundle Composition counterpart to assess_candidate (Phase 10.7,
    §12's addendum) - see this module's own docstring for the accept
    logic. Resolves the candidate's BundleComposition via
    GenerationAttempt.bundle_composition_id (never via
    GeneratedImage.generation_reference_set_id, which stays null for a
    bundle candidate - see BundleComposition's own docstring) and runs
    one independent Stage 1 Identity Validation per member.
    """
    attempt = db.get(GenerationAttempt, generated_image.generation_attempt_id)
    if attempt is None or attempt.bundle_composition_id is None:
        return StageResult(
            succeeded=False,
            error="This candidate has no Bundle Composition - use assess_candidate instead.",
        )

    members = list(
        db.query(BundleCompositionMember)
        .filter(BundleCompositionMember.bundle_composition_id == attempt.bundle_composition_id)
        .order_by(BundleCompositionMember.rank)
        .all()
    )
    if not members:
        return StageResult(succeeded=False, error="Bundle Composition has no members to validate against.")

    validation_result_ids: list[str] = []
    all_passed = True
    for member in members:
        stage_result = run_bundle_member_identity_validation(db, generated_image, member)
        if not stage_result.succeeded:
            return stage_result

        member_result = (
            db.query(ImageValidationResult)
            .filter(
                ImageValidationResult.generated_image_id == generated_image.id,
                ImageValidationResult.product_id == member.product_id,
                ImageValidationResult.is_current.is_(True),
            )
            .one()
        )
        validation_result_ids.append(member_result.id)
        all_passed = all_passed and bool(member_result.passed)

    photorealism_json: dict | None = None
    if all_passed:
        photorealism_json = _run_photorealism(db, generated_image)
        photorealism_score = _score_photorealism(photorealism_json)
        accepted = photorealism_score >= PHOTOREALISM_FLOOR
        overall_confidence_score = photorealism_score
    else:
        accepted = False
        overall_confidence_score = 0.0

    assessment = QualityAssessment(
        generated_image_id=generated_image.id,
        image_validation_result_id=None,
        image_validation_result_ids_json=validation_result_ids,
        photorealism_json=photorealism_json,
        overall_confidence_score=overall_confidence_score,
        accepted=accepted,
    )
    db.add(assessment)
    # Same real-commit reasoning as assess_candidate above - nothing
    # after this point to piggyback a commit on.
    db.commit()
    return assessment
