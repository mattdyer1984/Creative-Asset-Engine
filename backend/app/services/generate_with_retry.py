"""
Automatic Retry Loop — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §14). Chains
Decision Engine -> Generation Engine -> Quality Engine, per
`GenerationAttempt.retry_of_generation_attempt_id`, until some
candidate is accepted or `max_retries` is hit.

**Real adaptive retry (see MIGRATION_PLAN.md)**: §11's "reading *why* a
previous attempt failed... and changing strategy accordingly" was
deliberately deferred at Phase 10.2 (§19 item 3) since none of the
richer failure signals existed yet - they do now (Photorealism is
Phase 10.3, Stage 1/2 Identity/Creative Validation were already live).
`_summarize_rejection_reason` below builds a specific, real reason from
the previous attempt's best (highest-confidence) rejected candidate's
actual `QualityAssessment`/`ImageValidationResult` data - which exact
identity/creative field didn't preserve, or which photorealism checks
failed - not the generic "nothing was accepted" placeholder this loop
used to pass. `decide_generation_plan`'s `retry_reason` was already
carried through and persisted from Phase 10.2 onward specifically so
this could be added without a schema change (see decision_engine.py's
own docstring) - `generation_engine.py`'s three attempt functions now
thread it into `compile_generation_request`, which gives the model an
explicit, honest "here's specifically what was wrong, fix this"
instruction on retry - still quality_mode/creativity_level/candidate_count
unchanged between attempts, since those aren't what a rejection reason
would inform; only the prompt's content changes.

Deliberately **not** wired into `SLIDESHOW_STAGE_PIPELINE` or any
background/automatic flow, per §14's own explicit instruction - every
candidate is a real paid provider call (up to
`max_retries + 1` attempts * `candidate_count` candidates each), so
this must stay behind its own explicit, user-triggered endpoint
(`POST .../generate-creative`), never one `POST /analyze` away from
firing.

`bundle_members` (Phase 10.7, §12's addendum), when given, routes every
attempt through `run_bundle_generation_attempt`/`assess_bundle_candidate`
instead of the single-product pair - the retry loop's own shape (chain
attempts, pick the best accepted candidate) is identical either way,
only which Generation/Quality Engine entry point runs differs.

Story Slide feature (see MIGRATION_PLAN.md): a slide with no current
product appearance (checked once via `resolve_primary_appearance`, the
same helper `run_generation_attempt` already uses) routes every attempt
through `run_story_generation_attempt`/`assess_story_candidate` instead
- again, only which Generation/Quality Engine entry point runs differs;
the retry loop's own shape is unchanged. This is genuinely automatic,
not a caller-supplied flag - the same way "has a product" is decided
everywhere else in this codebase (Creative Specification, Product
Isolation).

`text_strategy` (Phase 10.8, §9/§15), when given, runs Text
Intelligence + the Rendering Engine on the accepted winner - once, not
per-candidate, since only the winner is ever going anywhere - and
persists the result as a `FinalOutput`. `None` (the default) skips
this entirely, exactly as it did before this phase, per
`GenerationPlan.text_strategy`'s own backward-compatibility reasoning.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import settings
from app.ai_providers.registry import default_registry
from app.models.creative_specification import CreativeSpecification
from app.models.final_output import FinalOutput
from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.models.image_validation_result import ImageValidationResult
from app.models.ocr_result import OCRResult
from app.models.product_lock_profile import ProductLockProfile
from app.models.quality_assessment import QualityAssessment
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.decision_engine import decide_generation_plan
from app.services.generation_engine import (
    run_bundle_generation_attempt,
    run_generation_attempt,
    run_story_generation_attempt,
)
from app.services.product_profile import extract_branding_text
from app.services.quality_engine import assess_bundle_candidate, assess_candidate, assess_story_candidate
from app.services.rendering_engine import render_final_output
from app.services.text_intelligence import build_text_assets
from app.prompts import generation as _generation_prompts
from app.services.timing_report import build_timing_breakdown, format_timing_breakdown
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.creative_specification_stage import resolve_primary_appearance

logger = logging.getLogger(__name__)

# A small, real bound, not "retry forever" - §14 calls for a
# "configured retry limit," this is Phase 10.2's default value for it.
DEFAULT_MAX_RETRIES = 1


def _log_timing_breakdown(db: Session, slide: Slide) -> None:
    """
    Optimisation & Stability Pass, Tier 1/2 (see MIGRATION_PLAN.md) -
    scoped by slide_id, not slideshow_id: every slide-scoped analysis
    stage (OCR, Product Isolation, Product Lock Profile, Creative
    Fingerprint, Scene Intelligence, Creative Specification) already
    records slide_id on its AnalysisRun rows, so this single query
    naturally covers this slide's whole journey - analysis through
    generation and validation - not just this call's own generation
    work. Best-effort: a reporting failure must never mask a real
    generation outcome already computed above.
    """
    try:
        breakdown = build_timing_breakdown(db, slide_id=slide.id)
        logger.info("Slide %s generation timing:\n%s", slide.id, format_timing_breakdown(breakdown))
    except Exception:
        logger.exception("Failed to build timing breakdown for slide %s", slide.id)


@dataclass
class CandidateAssessment:
    generated_image: GeneratedImage
    quality_assessment: QualityAssessment


@dataclass
class GenerationAttemptOutcome:
    attempt: GenerationAttempt
    candidates: list[CandidateAssessment]


@dataclass
class RetryLoopResult:
    attempts: list[GenerationAttemptOutcome]
    winner: CandidateAssessment | None
    final_output: FinalOutput | None = None


def _failed_check_reasons(checks: list[dict] | None) -> list[str]:
    return [check["reason"] for check in (checks or []) if not check["preserved"]]


def _summarize_rejection_reason(db: Session, candidate_assessments: list[CandidateAssessment]) -> str:
    """
    Real adaptive retry (see MIGRATION_PLAN.md and this module's own
    docstring) - a specific, actionable reason for the next attempt's
    prompt, not the old generic placeholder. Picks the highest-
    confidence rejected candidate (closest to passing - the most
    informative one to fix) and extracts the most fundamental failure
    reason available for it, in priority order: Stage 1 Identity >
    Stage 2 per-field creative > Photorealism > whatever
    overall_explanation says. A candidate can fail at any of these
    layers; a fixable identity problem is worth surfacing over a
    generic photorealism note, so identity is checked first.

    Handles all three GenerationEngine paths uniformly:
    single-product (image_validation_result_id), Bundle Composition
    (image_validation_result_ids_json, one member's failure is enough
    to explain), and Story Slide (neither - Photorealism only).
    """
    if not candidate_assessments:
        return _generation_prompts.RETRY_REASON.fragments["nothing_generated"]

    best = max(candidate_assessments, key=lambda c: c.quality_assessment.overall_confidence_score)
    qa = best.quality_assessment

    validation_result_ids: list[str] = []
    if qa.image_validation_result_id:
        validation_result_ids = [qa.image_validation_result_id]
    elif qa.image_validation_result_ids_json:
        validation_result_ids = list(qa.image_validation_result_ids_json)

    for result_id in validation_result_ids:
        result = db.get(ImageValidationResult, result_id)
        if result is None:
            continue
        identity_failures = _failed_check_reasons(result.identity_checks_json)
        if identity_failures:
            return _generation_prompts.RETRY_REASON.fragments["identity"] + "; ".join(identity_failures)
        field_failures = _failed_check_reasons(result.field_checks_json)
        if field_failures:
            return _generation_prompts.RETRY_REASON.fragments["fields"] + "; ".join(field_failures)
        if result.overall_explanation and not result.passed:
            return result.overall_explanation

    photorealism_reasons = (qa.photorealism_json or {}).get("reasons") or []
    if photorealism_reasons:
        # Style-aware opening. Telling an illustrated candidate it "didn't
        # look sufficiently realistic" made every retry drift further from
        # a source that is deliberately an illustration.
        return _style_quality_opening(db, best.generated_image) + "; ".join(photorealism_reasons)

    return _generation_prompts.RETRY_REASON.fragments["none_passed"]


def _packaging_text_for_winner(db: Session, slide: Slide) -> list[str]:
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md and
    text_intelligence.py's own docstring) - the winning candidate's
    product's own branding_text, so build_text_assets can exclude any
    OCR block that duplicates text already preserved on the packaging
    itself. `[]` (no product assigned, or no current Lock Profile yet)
    is a real, valid outcome - the filter simply has nothing to
    exclude, same tri-state discipline as everywhere else this
    codebase handles a not-yet-available prerequisite.
    """
    appearance = resolve_primary_appearance(slide.current_product_appearances)
    if appearance is None:
        return []
    lock_profile = db.scalars(
        select(ProductLockProfile).where(
            ProductLockProfile.product_id == appearance.product_id,
            ProductLockProfile.is_current.is_(True),
        )
    ).first()
    if lock_profile is None:
        return []
    return extract_branding_text(lock_profile)


def _render_with_ownership(db: Session, slide: Slide, source_bytes: bytes):
    """
    The ownership-aware path (ADR 0001, Package E), behind
    `CAE_TYPOGRAPHY_RENDERER_ENABLED`.

    Reads what analysis already decided rather than re-deriving it: the
    persisted ownership artifact (E3), the Composition Contract (E1) and the
    Creative Project Profile (E2). Re-deriving here would let the image be
    rendered against a different set of decisions from the one recorded, so
    the manifest would describe work that did not happen.

    Returns `(bytes, manifest)`, or `(None, None)` when the prerequisites are
    absent - a slide analysed before this stage existed must fall through to
    the legacy renderer rather than lose its text.
    """
    from app.services.composition_contract import contract_of, get_current_contract
    from app.services.creative_project_profile import (
        effective_copy_policy,
        effective_overlay_policy,
        effective_primary_text_mode,
        effective_typography_system,
        get_current_profile,
    )
    from app.services.ownership_artifact import decisions_of, get_current
    from app.services.text_ownership import OwnershipPlan
    from app.services.typography_pipeline import apply_typography

    artifact = get_current(db, slide.id)
    if artifact is None:
        logger.info(
            "slide %s has no ownership artifact - falling back to the legacy "
            "renderer rather than rendering without ownership", slide.id,
        )
        return None, None

    profile = get_current_profile(db, slide.slideshow_id)
    system = effective_typography_system(profile) if profile else None
    plan = OwnershipPlan(decisions=decisions_of(artifact))

    return apply_typography(
        source_bytes,
        plan,
        system,
        profile_id=profile.id if profile else None,
        contract=contract_of(get_current_contract(db, slide.id)),
        effective_policies={
            "text_mode": str(effective_primary_text_mode(profile)) if profile else "unknown",
            "copy_policy": str(effective_copy_policy(profile)) if profile else "unknown",
            "overlay_policy": str(effective_overlay_policy(profile)) if profile else "unknown",
        },
    )


def _render_final_output_for_winner(
    db: Session, slide: Slide, winner: CandidateAssessment, text_strategy: str
) -> FinalOutput:
    ocr_result = db.get(OCRResult, slide.current_ocr_result_id) if slide.current_ocr_result_id else None
    text_generation_provider = default_registry.text_generation() if text_strategy == "ai_rewrite" else None
    text_assets = build_text_assets(
        text_strategy,
        ocr_result,
        text_generation_provider=text_generation_provider,
        packaging_text=_packaging_text_for_winner(db, slide),
        db=db,
    )

    source_bytes = Path(winner.generated_image.file_path).read_bytes()

    manifest = None
    rendered_bytes = None
    if settings.typography_renderer_enabled:
        rendered_bytes, manifest = _render_with_ownership(db, slide, source_bytes)
        if manifest is not None and not manifest.accounts_for_every_block():
            # Every block must land in exactly one outcome bucket. One that
            # vanished is the failure this manifest exists to make visible,
            # so it is not allowed to pass silently.
            manifest.warnings.append(
                "manifest does not account for every block - review this output"
            )
            logger.warning("slide %s: render manifest is incomplete", slide.id)
    if rendered_bytes is None:
        rendered_bytes = render_final_output(source_bytes, text_assets)

    final_output = FinalOutput(
        generation_attempt_id=winner.generated_image.generation_attempt_id,
        generated_image_id=winner.generated_image.id,
        text_assets_json=text_assets,
        render_manifest_json=manifest.model_dump(mode="json") if manifest else None,
        file_path="",
    )
    db.add(final_output)
    db.flush()

    saved_path = storage.save_final_output(slide.id, final_output.id, rendered_bytes)
    final_output.file_path = str(saved_path)
    # A real commit - the last write for this call chain, with nothing
    # after it to piggyback a commit on, same reasoning as every other
    # "last write in the chain" fix this session already made
    # (quality_engine.assess_candidate, the is_current flip below).
    db.commit()
    return final_output


def generate_with_retry(
    db: Session,
    slideshow: Slideshow,
    quality_mode: str,
    *,
    slide: Slide | None = None,
    creativity_level: str = "conservative",
    max_retries: int = DEFAULT_MAX_RETRIES,
    bundle_members: list[dict] | None = None,
    text_strategy: str | None = None,
    user_feedback: str | None = None,
) -> RetryLoopResult | StageResult:
    """
    slide (Generate All, see MIGRATION_PLAN.md) - `None` (the default,
    and every pre-existing call site's behavior) resolves to
    `slideshow.primary_slide`, exactly as this function always did.
    Every other line in this function already reads `slide`, not
    `slideshow.primary_slide` - this was the one hardcoded line
    blocking generation on any other slide in the slideshow.

    Real-world-diagnosed fix (Generate All, see MIGRATION_PLAN.md): the
    Creative Specification used to be resolved from
    `slideshow.current_creative_specification_id` (one shared row per
    slideshow, always built from the *primary* slide) regardless of
    which `slide` was passed in here - a real cross-slide contamination
    bug, confirmed live (a non-primary slide's generated image was
    built from the primary slide's own scene). Creative Specification is
    now slide-scoped (`Slide.current_creative_specification_id`), so
    this resolves the *actual* `slide` being generated, not the
    slideshow's shared pointer.

    user_feedback (Generate All, see MIGRATION_PLAN.md) - the same
    free-text note carried unchanged across every retry attempt within
    this one call, deliberately separate from `retry_reason` below
    (that's the internal, per-attempt auto-retry signal; this is one
    user note for the whole call).
    """
    slide = slide if slide is not None else slideshow.primary_slide
    if slide.current_creative_specification_id is None:
        return StageResult(
            succeeded=False,
            error="No Creative Specification available yet for this slide - run that stage first.",
        )
    creative_specification = db.get(
        CreativeSpecification, slide.current_creative_specification_id
    )
    if creative_specification is None:
        return StageResult(
            succeeded=False,
            error="Creative Specification referenced by the Slide no longer exists.",
        )

    is_story_slide = resolve_primary_appearance(slide.current_product_appearances) is None

    attempts: list[GenerationAttemptOutcome] = []
    retry_of_id: str | None = None
    retry_reason: str | None = None

    for _ in range(max_retries + 1):
        plan = decide_generation_plan(
            quality_mode,
            creativity_level=creativity_level,
            retry_of_generation_attempt_id=retry_of_id,
            retry_reason=retry_reason,
            bundle_members=bundle_members,
            text_strategy=text_strategy,
            user_feedback=user_feedback,
        )
        if is_story_slide:
            attempt_result = run_story_generation_attempt(db, slide, creative_specification, plan)
        elif plan.bundle_members:
            attempt_result = run_bundle_generation_attempt(db, slide, creative_specification, plan)
        else:
            attempt_result = run_generation_attempt(db, slide, creative_specification, plan)
        if isinstance(attempt_result, StageResult):
            # Can't even start (no product assigned, empty Library) -
            # the same failure would recur on every retry, so stop
            # immediately rather than burning the retry budget on
            # attempts that can never succeed.
            return attempt_result

        candidate_assessments: list[CandidateAssessment] = []
        for candidate in attempt_result.candidates:
            if is_story_slide:
                assessment_result = assess_story_candidate(db, candidate)
            elif plan.bundle_members:
                assessment_result = assess_bundle_candidate(db, candidate)
            else:
                assessment_result = assess_candidate(db, candidate)
            if isinstance(assessment_result, StageResult):
                # This one candidate's validation couldn't run (e.g. no
                # immutable Product Profile fields yet) - treated as a
                # non-accepted candidate, not a fatal error for the
                # whole attempt; other candidates may still validate.
                continue
            candidate_assessments.append(
                CandidateAssessment(generated_image=candidate, quality_assessment=assessment_result)
            )

        attempts.append(
            GenerationAttemptOutcome(attempt=attempt_result.attempt, candidates=candidate_assessments)
        )

        accepted = [c for c in candidate_assessments if c.quality_assessment.accepted]
        if accepted:
            winner = max(accepted, key=lambda c: c.quality_assessment.overall_confidence_score)
            db.query(GeneratedImage).filter(
                GeneratedImage.slide_id == slide.id,
                GeneratedImage.is_current.is_(True),
            ).update({"is_current": False})
            winner.generated_image.is_current = True
            # A real commit - the is_current flip is this loop's last
            # write, with nothing after it to piggyback a commit on
            # (same reasoning as quality_engine.assess_candidate's own
            # fix); a flush-only write here would roll back once the
            # request's session closes, silently leaving no "current"
            # generated image at all despite a real accepted winner.
            db.commit()

            final_output = None
            if plan.text_strategy is not None:
                final_output = _render_final_output_for_winner(db, slide, winner, plan.text_strategy)

            _log_timing_breakdown(db, slide)
            return RetryLoopResult(attempts=attempts, winner=winner, final_output=final_output)

        retry_of_id = attempt_result.attempt.id
        retry_reason = _summarize_rejection_reason(db, candidate_assessments)

    _log_timing_breakdown(db, slide)
    return RetryLoopResult(attempts=attempts, winner=None)


def _style_quality_opening(db: Session, generated_image: GeneratedImage) -> str:
    """
    The retry-feedback opening that matches the SOURCE medium.

    Never returns wording that asks for a change of medium - see the
    safeguard test in tests/test_source_style_policy.py, which asserts
    an illustrated source can never be told to become a photograph.
    """
    from app.services.quality_engine import _classify_generated_image_style
    from app.services.source_style import RenderingFamily

    fragments = _generation_prompts.RETRY_REASON.fragments
    if generated_image is None:
        return fragments["photorealism"]

    classification = _classify_generated_image_style(db, generated_image)
    if not classification.is_confident:
        return fragments["photorealism"]
    return {
        RenderingFamily.PHOTOGRAPHIC: fragments["photorealism"],
        RenderingFamily.ILLUSTRATED: fragments["style_illustrated"],
        RenderingFamily.RENDER: fragments["style_render"],
        RenderingFamily.MIXED: fragments["style_mixed"],
    }.get(classification.family, fragments["photorealism"])


def describe_rejection(db: Session, assessment: QualityAssessment) -> list[str]:
    """
    Every reason a candidate was rejected, for display.

    `_summarize_rejection_reason` above picks the single most useful
    reason to feed the next attempt's prompt; this returns the full list
    for a human deciding whether to accept the candidate anyway. Same
    source data, different audience - which is why they are separate
    rather than one function trying to serve both.
    """
    if assessment.accepted:
        return []

    reasons: list[str] = []
    validation_ids: list[str] = []
    if assessment.image_validation_result_id:
        validation_ids = [assessment.image_validation_result_id]
    elif assessment.image_validation_result_ids_json:
        validation_ids = list(assessment.image_validation_result_ids_json)

    for result_id in validation_ids:
        result = db.get(ImageValidationResult, result_id)
        if result is None:
            continue
        for check in result.identity_checks_json or []:
            if not check.get("preserved"):
                reasons.append(f"Product identity - {check['field_name']}: {check['reason']}")
        for check in result.field_checks_json or []:
            if not check.get("preserved"):
                reasons.append(f"Product detail - {check['field_name']}: {check['reason']}")

    for reason in (assessment.photorealism_json or {}).get("reasons") or []:
        reasons.append(f"Image quality - {reason}")

    return reasons
