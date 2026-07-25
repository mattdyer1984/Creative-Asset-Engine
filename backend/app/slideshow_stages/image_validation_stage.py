"""
Image Validation Stage — Phase 8.4 of the Generation -> Validation proof
of loop; extended in Phase 9.4 of Product Lock v2 (see MIGRATION_PLAN.md's
"ADR: Canonical Product Reference" §7) with Stage 1 Identity Validation,
run before the original per-field creative check (now "Stage 2").

Reuses VisionAnalysisProvider unchanged - no new AI capability needed,
per the architecture direction ("Validation - reuses
VisionAnalysisProvider, no new provider"). `passed` is computed here
from returned per-field judgments, never asked of the AI as a bare
boolean, matching this codebase's standing rule that anything derivable
from known facts is assembled directly.

Deliberate signature difference from every SlideshowAnalysisStage:
`run(db, generated_image)`, not `run(db, slideshow)`. Validation targets
one specific GeneratedImage instance (there can be several over time for
one slide), never "whichever is current for the slideshow" - the
Protocol shape that fits every other stage genuinely doesn't fit this
one. Deliberately NOT added to SLIDESHOW_STAGE_PIPELINE either way - a
real vision-analysis call per validation, explicitly triggered via its
own endpoint, not automatic.

Stage 1 - Identity Validation (Phase 9.4): compares the generated image
directly against the reference images from the SAME GenerationReferenceSet
that was actually used to generate it (GeneratedImage.
generation_reference_set_id) - not a fresh, independent Library pull.
Short-circuits per the ADR's explicit design: if identity fails, Stage 2
never runs, saving a real vision call on every clear identity failure.
A known, acknowledged limitation (not solved here): this only tests
"did the model faithfully render the images it was given," not full
independent identity verification against angles the model never saw -
see the ADR §7/§12 for the full reasoning, and §9's frontend section for
how this should be surfaced honestly rather than overclaimed.

Tri-state, matching this codebase's existing staleness/narrative-beat
discipline: if the GeneratedImage has no generation_reference_set_id
(every row created before this ADR shipped), Stage 1 is skipped
entirely - identity_passed/identity_checks_json stay null ("unknown,"
not "failed"), and Stage 2 runs exactly as it did before this phase.
`passed`'s meaning is repurposed, not its shape: "identity passed AND
creative passed" when identity was actually checked, "creative passed"
alone when it wasn't (never a null-swallows-True bug from a naive
boolean AND with None).
"""

import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_IMAGE_VALIDATION
from app.models.bundle_composition import BundleCompositionMember
from app.models.generated_image import GeneratedImage
from app.models.image_validation_result import ImageValidationResult
from app.models.product import Product
from app.models.slide import Slide
from app.services.product_profile import assemble_product_profile
from app.services.prompt_compiler import format_attribute_value
from app.services.reference_selection import get_reference_image_paths
from app.slideshow_stages.base import StageResult
from app.prompts import validation as _validation_prompts
from app.slideshow_stages.creative_specification_stage import resolve_primary_appearance
from app.services.provider_call_log import record_provider_call
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

IMAGE_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "field_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string"},
                    "preserved": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["field_name", "preserved", "reason"],
                "additionalProperties": False,
            },
        },
        "overall_explanation": {"type": "string"},
    },
    "required": ["field_checks", "overall_explanation"],
    "additionalProperties": False,
}

# Same {field_name, preserved, reason} shape as IMAGE_VALIDATION_SCHEMA,
# minus overall_explanation - Stage 1 is a fixed, generic geometric/
# visual-identity checklist (the request's own field list), not derived
# per-product from the canonical Product Profile the way Stage 2's
# fields are.
IDENTITY_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "field_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string"},
                    "preserved": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["field_name", "preserved", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["field_checks"],
    "additionalProperties": False,
}

# The field list is prompt content, so it now lives with the prompt
# (WP-3) - editing it there moves the prompt's content hash. Re-exported
# under its original name so nothing that reads it has to change.
IDENTITY_FIELDS = _validation_prompts.IDENTITY_FIELDS


def _build_prompt(immutable_fields: list[tuple[str, str]]) -> str:
    field_lines = "\n".join(f"- field_name \"{name}\": expected value = {value}" for name, value in immutable_fields)
    return _validation_prompts.CREATIVE_FIDELITY.render(field_lines=field_lines)


def _build_identity_prompt() -> str:
    return _validation_prompts.IDENTITY.render()


def _resolve_product(db: Session, generated_image: GeneratedImage) -> Product | None:
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): GeneratedImage has
    no product_id of its own. This used to resolve via
    `CreativeSpecification.product_lock_profile_id` - but CreativeSpecification
    is one row per Slideshow, always built from the *primary* slide
    (creative_specification_stage.py), so that chain silently pointed at
    the primary slide's product regardless of which slide's
    GeneratedImage was actually being validated - harmless while
    generation was primary-slide-only, but wrong the moment a
    non-primary slide with a different assigned product generates an
    image (Generate All, see MIGRATION_PLAN.md). Resolved instead via
    the image's own `slide_id` -> that slide's current product
    appearance - the exact same resolution
    app.services.generation_engine.run_generation_attempt already used
    to pick the product Generation was actually told to preserve for
    this specific slide, reused here rather than re-derived so
    Validation and Generation can never disagree about which product a
    given GeneratedImage belongs to.
    """
    slide = db.get(Slide, generated_image.slide_id)
    if slide is None:
        return None
    appearance = resolve_primary_appearance(slide.current_product_appearances)
    if appearance is None:
        return None
    return db.get(Product, appearance.product_id)


class SlideImageValidationStage:
    name = "image_validation"

    def run(self, db: Session, generated_image: GeneratedImage) -> StageResult:
        product = _resolve_product(db, generated_image)
        if product is None:
            return StageResult(
                succeeded=False,
                error="Could not resolve the product this generated image is meant to depict.",
            )

        vision_provider = default_registry.vision()

        analysis_run = start_analysis_run(
            db,
            # generated_image.slide_id (Optimisation & Stability Pass, Tier
            # 2 - see MIGRATION_PLAN.md): this AnalysisRun previously
            # carried neither slide_id nor slideshow_id at all, so
            # timing_report.build_timing_breakdown's per-slide query
            # couldn't include Validation - a real, available fact
            # (validation targets exactly one GeneratedImage, which
            # belongs to exactly one slide), not a guess.
            slide_id=generated_image.slide_id,
            analysis_type=ANALYSIS_TYPE_IMAGE_VALIDATION,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=True,
        )
        provider_call_ms = 0.0
        usage: dict = {}

        try:
            generated_image_bytes = Path(generated_image.file_path).read_bytes()

            identity_passed: bool | None = None
            identity_checks: list[dict] | None = None

            if generated_image.generation_reference_set_id is not None:
                reference_paths = get_reference_image_paths(
                    db, generated_image.generation_reference_set_id
                )
                if reference_paths:
                    reference_bytes = [Path(path).read_bytes() for path in reference_paths]
                    identity_usage: dict = {}
                    call_start = time.perf_counter()
                    identity_result = vision_provider.analyze_creative(
                        image_bytes=[generated_image_bytes, *reference_bytes],
                        prompt_spec={"prompt": _build_identity_prompt(), "schema_name": "identity_validation"},
                        response_schema=IDENTITY_VALIDATION_SCHEMA,
                        usage_sink=identity_usage,
                    )
                    provider_call_ms += (time.perf_counter() - call_start) * 1000
                    _accumulate_usage(usage, identity_usage)
                    # Phase 1 remediation (WP-2): recorded per CALL. This
                    # stage makes TWO provider calls under ONE
                    # AnalysisRun (Stage 1 identity here, Stage 2
                    # creative below), so folding them into the run would
                    # either double-count or lose per-call attribution.
                    record_provider_call(
                        db,
                        provider=vision_provider.provider,
                        model=vision_provider.model,
                        capability="vision_analysis",
                        usage=identity_usage,
                        provider_latency_ms=(time.perf_counter() - call_start) * 1000,
                        analysis_run_id=analysis_run.id,
                        generated_image_id=generated_image.id,
                        slide_id=generated_image.slide_id,
                        slideshow_id=generated_image.slideshow_id,
                    )
                    identity_checks = identity_result["field_checks"]
                    identity_passed = bool(identity_checks) and all(
                        check["preserved"] for check in identity_checks
                    )

            if identity_passed is False:
                # Short-circuit (ADR §7): Stage 2 never runs, saving a
                # real vision call on a clear identity failure.
                passed = False
                field_checks: list[dict] = []
                overall_explanation = (
                    "Identity validation failed - the generated image does not "
                    "faithfully preserve the product's visual identity shown in "
                    "its reference images. Creative validation was skipped."
                )
            else:
                product_profile = assemble_product_profile(db, product)
                immutable_fields = [
                    (field_name, field.value)
                    for field_name, field in product_profile.fields.items()
                    if field.classification == "immutable"
                ]
                if not immutable_fields:
                    return StageResult(
                        succeeded=False,
                        error=(
                            "No immutable Product Profile fields available yet - "
                            "run Product Lock Profile or a source import first."
                        ),
                    )

                prompt = _build_prompt(
                    [(name, format_attribute_value(value)) for name, value in immutable_fields]
                )
                creative_usage: dict = {}
                call_start = time.perf_counter()
                result = vision_provider.analyze_creative(
                    image_bytes=generated_image_bytes,
                    prompt_spec={"prompt": prompt, "schema_name": "image_validation"},
                    response_schema=IMAGE_VALIDATION_SCHEMA,
                    usage_sink=creative_usage,
                )
                provider_call_ms += (time.perf_counter() - call_start) * 1000
                _accumulate_usage(usage, creative_usage)
                # The second of this stage's two calls - see the note on
                # the identity call above.
                record_provider_call(
                    db,
                    provider=vision_provider.provider,
                    model=vision_provider.model,
                    capability="vision_analysis",
                    usage=creative_usage,
                    provider_latency_ms=(time.perf_counter() - call_start) * 1000,
                    analysis_run_id=analysis_run.id,
                    generated_image_id=generated_image.id,
                    slide_id=generated_image.slide_id,
                    slideshow_id=generated_image.slideshow_id,
                )

                field_checks = result["field_checks"]
                creative_passed = bool(field_checks) and all(
                    check["preserved"] for check in field_checks
                )
                overall_explanation = result["overall_explanation"]
                # identity_passed is True or None (skipped) here - only
                # fold it into `passed` when it was actually checked.
                passed = creative_passed if identity_passed is None else (identity_passed and creative_passed)

            db.query(ImageValidationResult).filter(
                ImageValidationResult.generated_image_id == generated_image.id,
                ImageValidationResult.is_current.is_(True),
            ).update({"is_current": False})

            validation_result = ImageValidationResult(
                analysis_run_id=analysis_run.id,
                generated_image_id=generated_image.id,
                product_id=product.id,
                passed=passed,
                field_checks_json=field_checks,
                overall_explanation=overall_explanation,
                identity_passed=identity_passed,
                identity_checks_json=identity_checks,
            )
            db.add(validation_result)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        return mark_succeeded(
            db,
            analysis_run,
            provider_call_ms=provider_call_ms,
            usage=usage,
            # This stage records its own per-CALL rows above (two calls
            # under one run) - opting out prevents double counting.
            emit_provider_call=False,
        )


def _accumulate_usage(total: dict, call_usage: dict) -> None:
    """Sums token counts across this Stage's up-to-two analyze_creative calls into one AnalysisRun."""
    for key in ("prompt_tokens", "completion_tokens"):
        value = call_usage.get(key)
        if value is not None:
            total[key] = total.get(key, 0) + value


def run_bundle_member_identity_validation(
    db: Session, generated_image: GeneratedImage, member: BundleCompositionMember
) -> StageResult:
    """
    Stage 1 Identity Validation only, run independently for one Bundle
    Composition member (Phase 10.7, §12's "Bundle Composition" addendum)
    - "every product in the scene must still retain its own canonical
    identity, reference set and validation," per the user's own
    explicit instruction. Compares the generated (bundle) image against
    THIS member's own GenerationReferenceSet, exactly the same
    mechanism SlideImageValidationStage.run's Stage 1 already uses for
    a single-product image - reused directly (_build_identity_prompt,
    IDENTITY_VALIDATION_SCHEMA), just addressed at one member instead
    of the whole image.

    Deliberately does NOT run Stage 2 (the text-field creative check):
    that depends on the single Creative Specification -> Product Lock
    Profile -> Product chain _resolve_product uses, which has no
    well-defined per-member analogue for a scene composed of several
    distinct products - a genuine, flagged scope cut (see
    app.services.quality_engine.assess_bundle_candidate), not an
    oversight. `passed` on the persisted row is therefore
    identity_passed alone here, unlike the single-product path's
    identity-AND-creative combination.

    Persists its own ImageValidationResult row, is_current-scoped to
    (generated_image_id, product_id) rather than the whole image - a
    bundle image legitimately has several *simultaneously* current
    results, one per member, unlike the single-product path's "exactly
    one current result per image" invariant.
    """
    product = db.get(Product, member.product_id)
    if product is None:
        return StageResult(
            succeeded=False, error=f"Product {member.product_id} referenced by this bundle member no longer exists."
        )

    reference_paths = get_reference_image_paths(db, member.generation_reference_set_id)
    if not reference_paths:
        return StageResult(
            succeeded=False,
            error=f"Bundle member's Generation Reference Set for product {product.id} has no images.",
        )

    vision_provider = default_registry.vision()
    analysis_run = start_analysis_run(
        db,
        slide_id=generated_image.slide_id,
        analysis_type=ANALYSIS_TYPE_IMAGE_VALIDATION,
        provider=vision_provider.provider,
        model_name=vision_provider.model,
        durable=True,
    )

    try:
        generated_image_bytes = Path(generated_image.file_path).read_bytes()
        reference_bytes = [Path(path).read_bytes() for path in reference_paths]
        usage: dict = {}
        call_start = time.perf_counter()
        identity_result = vision_provider.analyze_creative(
            image_bytes=[generated_image_bytes, *reference_bytes],
            prompt_spec={"prompt": _build_identity_prompt(), "schema_name": "identity_validation"},
            response_schema=IDENTITY_VALIDATION_SCHEMA,
            usage_sink=usage,
        )
        provider_call_ms = (time.perf_counter() - call_start) * 1000
        # Bundle Composition path - one identity call per member product,
        # each its own billable call and so its own ProviderCall row.
        record_provider_call(
            db,
            provider=vision_provider.provider,
            model=vision_provider.model,
            capability="vision_analysis",
            usage=usage,
            provider_latency_ms=provider_call_ms,
            analysis_run_id=analysis_run.id,
            generated_image_id=generated_image.id,
            slide_id=generated_image.slide_id,
            slideshow_id=generated_image.slideshow_id,
        )
        identity_checks = identity_result["field_checks"]
        identity_passed = bool(identity_checks) and all(check["preserved"] for check in identity_checks)

        db.query(ImageValidationResult).filter(
            ImageValidationResult.generated_image_id == generated_image.id,
            ImageValidationResult.product_id == member.product_id,
            ImageValidationResult.is_current.is_(True),
        ).update({"is_current": False})

        db.add(
            ImageValidationResult(
                analysis_run_id=analysis_run.id,
                generated_image_id=generated_image.id,
                product_id=member.product_id,
                passed=identity_passed,
                field_checks_json=[],
                overall_explanation=(
                    "Bundle Composition member validation - Stage 1 Identity only, "
                    "see run_bundle_member_identity_validation's own docstring for why "
                    "Stage 2 does not run per-member."
                ),
                identity_passed=identity_passed,
                identity_checks_json=identity_checks,
            )
        )
        db.flush()

    except Exception as exc:
        return mark_failed(db, analysis_run, exc, rollback=True)

    return mark_succeeded(
            db,
            analysis_run,
            provider_call_ms=provider_call_ms,
            usage=usage,
            # This stage records its own per-CALL rows above (two calls
            # under one run) - opting out prevents double counting.
            emit_provider_call=False,
        )
