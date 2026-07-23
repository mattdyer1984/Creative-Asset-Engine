"""
Generation Engine — Phase 10.2 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §12). Makes image
generation candidate-count-aware: one `GenerationAttempt` groups N
`GeneratedImage` candidates, exactly mirroring how N
`GenerationReferenceSetImage` rows already belong to one
`GenerationReferenceSet` (Product Lock v2 §3).

Extends the existing single-call machinery rather than replacing it -
reuses `select_reference_images`/`get_reference_image_paths`
(Product Lock v2 §6) and `compile_generation_request` (§6/Phase 8.2)
exactly as `SlideImageGenerationStage` (Phase 8.3/9.3) already does.
That stage and its `POST .../generate-image` endpoint are left
completely untouched - they remain the simple, single-candidate path;
this module is a genuinely new, additive path alongside it, used by
the new `POST .../generate-creative` retry-loop endpoint.

One Reference Set per attempt, not per candidate: all N candidates in
one GenerationAttempt are alternate samples of the *same* scene/plan,
so Reference Selection runs once and every candidate's
`GeneratedImage.generation_reference_set_id` points at that same Set -
Stage 1 Identity Validation (run once per candidate, see
quality_engine.py) needs that field populated on each row regardless.
`GenerationReferenceSet.generated_image_id` (the older, singular
reverse-link field from Product Lock v2 §3, meant for a Set that fed
exactly one image) is deliberately left null here rather than
arbitrarily pointing at one candidate - it genuinely fed several,
and nothing reads that field for lookup (only the forward
`GeneratedImage.generation_reference_set_id` direction is ever
queried), so leaving it null is honest, not a regression.

**Creative Intelligence integration (Phase 10.4, §8)**: if the slide
has a current `SceneAnalysis`, this Stage calls
`creative_intelligence.optimize_scene_description` once per attempt
(same "once per attempt, not per candidate" reasoning as Reference
Selection above - every candidate samples the same optimized scene) and
merges the result into a *copy* of the Creative Specification's
`background_environment` field before compiling - never mutating the
persisted `CreativeSpecification` row itself. Not persisted as a
separate artifact: the optimized description flows into the compiled
prompt exactly like every other scene detail, so it's already
traceable via each candidate's own `GeneratedImage.prompt_used`, the
same "record what actually happened" mechanism this codebase already
relies on everywhere else. Tri-state: a slide with no `SceneAnalysis`
yet (pre-10.4 slideshow, or the pipeline hasn't rerun) skips this
entirely and compiles the original, un-enriched specification -
exactly how generation already worked before this sub-phase.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_GENERATED_IMAGE
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.creative_specification import CreativeSpecification
from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.models.marketing_analysis import MarketingAnalysis
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.models.scene_analysis import SceneAnalysis
from app.models.slide import Slide
from app.services.creative_intelligence import optimize_scene_description
from app.services.decision_engine import GenerationPlan
from app.services.prompt_compiler import compile_generation_request
from app.services.reference_selection import get_reference_image_paths, select_reference_images
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.creative_specification_stage import resolve_primary_appearance
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


def _enriched_creative_specification(
    db: Session, slide: Slide, product: Product, creative_specification: CreativeSpecification, plan: GenerationPlan
) -> dict:
    """
    Returns `creative_specification.structured_json`, or a copy with
    `background_environment` replaced by Creative Intelligence's
    optimized scene description when a SceneAnalysis exists for this
    slide - never mutates the persisted row.
    """
    structured = creative_specification.structured_json
    if not slide.current_scene_analysis_id:
        return structured

    scene_analysis = db.get(SceneAnalysis, slide.current_scene_analysis_id)
    if scene_analysis is None:
        return structured

    fingerprint = (
        db.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
        if slide.current_creative_fingerprint_id
        else None
    )
    marketing_analysis = (
        db.get(MarketingAnalysis, slide.slideshow.current_marketing_analysis_id)
        if slide.slideshow.current_marketing_analysis_id
        else None
    )
    lock_profile = db.scalars(
        select(ProductLockProfile).where(
            ProductLockProfile.product_id == product.id,
            ProductLockProfile.is_current.is_(True),
        )
    ).first()

    result = optimize_scene_description(
        scene_analysis,
        visual_style=(fingerprint.structured_json.get("visual_style", "") if fingerprint else ""),
        marketing_narrative=(marketing_analysis.narrative_text if marketing_analysis else ""),
        product_category=(lock_profile.structured_json.get("product_category", "") if lock_profile else ""),
        creativity_level=plan.creativity_level,
    )

    return {**structured, "background_environment": result["optimized_scene_description"]}


@dataclass
class GenerationAttemptResult:
    attempt: GenerationAttempt
    candidates: list[GeneratedImage]


def run_generation_attempt(
    db: Session, slide: Slide, creative_specification: CreativeSpecification, plan: GenerationPlan
) -> GenerationAttemptResult | StageResult:
    """
    Runs one full GenerationAttempt: resolves the slide's primary
    product, selects a Reference Set once, then generates
    `plan.candidate_count` independent candidates from the same
    compiled request. Returns a StageResult on any failure that
    prevents generation from starting at all (no product, no Library) -
    the same "clean, explained failure" shape every other Stage in this
    codebase already returns, so callers don't need a second error
    convention.
    """
    current_appearance = resolve_primary_appearance(slide.current_product_appearances)
    if current_appearance is None:
        return StageResult(
            succeeded=False, error="No product assigned to this slide yet - assign one first."
        )
    product = db.get(Product, current_appearance.product_id)
    if product is None:
        return StageResult(
            succeeded=False,
            error="Product referenced by the Slide's current appearance no longer exists.",
        )

    image_provider = default_registry.image_generation(plan.provider)

    generation_reference_set = select_reference_images(
        db, product.id, creative_specification.structured_json, image_provider.capabilities
    )
    if generation_reference_set is None:
        return StageResult(
            succeeded=False,
            error=(
                "No Generation Reference Set available - the product's Canonical "
                "Reference Library is empty. Run Reference Scoring first "
                "(POST /api/products/{id}/score-references)."
            ),
        )

    reference_image_paths = get_reference_image_paths(db, generation_reference_set.id)
    enriched_specification = _enriched_creative_specification(
        db, slide, product, creative_specification, plan
    )
    request = compile_generation_request(enriched_specification, reference_image_paths)

    attempt = GenerationAttempt(
        slide_id=slide.id,
        creative_specification_id=creative_specification.id,
        generation_reference_set_id=generation_reference_set.id,
        quality_mode=plan.quality_mode,
        decision_json=plan.to_dict(),
        retry_of_generation_attempt_id=plan.retry_of_generation_attempt_id,
    )
    db.add(attempt)
    db.flush()

    candidates: list[GeneratedImage] = []
    for candidate_index in range(plan.candidate_count):
        analysis_run = start_analysis_run(
            db,
            slide_id=slide.id,
            analysis_type=ANALYSIS_TYPE_GENERATED_IMAGE,
            provider=image_provider.provider,
            model_name=image_provider.model,
            durable=True,
        )
        try:
            result = image_provider.generate_image(request)

            generated_image = GeneratedImage(
                analysis_run_id=analysis_run.id,
                slideshow_id=slide.slideshow_id,
                slide_id=slide.id,
                creative_specification_id=creative_specification.id,
                generation_reference_set_id=generation_reference_set.id,
                generation_attempt_id=attempt.id,
                candidate_index=candidate_index,
                is_current=False,  # candidates aren't "the" current generation until one is accepted
                provider=result.provider,
                model_name=result.model,
                prompt_used=result.prompt_used,
                seed=result.seed,
                generation_time_seconds=result.generation_time_seconds,
                file_path="",
            )
            db.add(generated_image)
            db.flush()

            saved_path = storage.save_generated_image(
                slide.id, generated_image.id, result.image_bytes
            )
            generated_image.file_path = str(saved_path)
            db.flush()

        except Exception as exc:
            mark_failed(db, analysis_run, exc, rollback=True)
            continue

        mark_succeeded(db, analysis_run)
        candidates.append(generated_image)

    return GenerationAttemptResult(attempt=attempt, candidates=candidates)
