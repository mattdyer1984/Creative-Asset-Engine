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

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_IMAGE_VALIDATION
from app.models.bundle_composition import BundleCompositionMember
from app.models.creative_specification import CreativeSpecification
from app.models.generated_image import GeneratedImage
from app.models.image_validation_result import ImageValidationResult
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.services.product_profile import assemble_product_profile
from app.services.prompt_compiler import format_attribute_value
from app.services.reference_selection import get_reference_image_paths
from app.slideshow_stages.base import StageResult
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

IDENTITY_FIELDS = [
    "silhouette",
    "aspect_ratio",
    "cap_geometry",
    "corners_edges",
    "brand_placement",
    "typography_placement",
    "color",
    "materials",
    "packaging",
]


def _build_prompt(immutable_fields: list[tuple[str, str]]) -> str:
    field_lines = "\n".join(f"- field_name \"{name}\": expected value = {value}" for name, value in immutable_fields)
    return (
        "This image was generated to recreate a marketing creative for a "
        "specific product while preserving the product's immutable "
        "physical characteristics. For EACH of the fields listed below, "
        "judge whether the generated image preserves that field's exact "
        "expected value - return exactly one field_checks entry per "
        "field below. field_name in your response must be ONLY the short "
        "field_name given in quotes below (e.g. \"brand\"), never the "
        "expected value or the two combined. Set preserved=true or "
        "preserved=false and give a short reason explaining your "
        "judgment. Then give one overall_explanation summarizing the "
        "assessment across every field.\n\n"
        f"Fields to check:\n{field_lines}"
    )


def _build_identity_prompt() -> str:
    field_lines = "\n".join(f'- "{name}"' for name in IDENTITY_FIELDS)
    return (
        "The first image is a newly generated marketing creative. Every "
        "image after it is an official reference photo of the real "
        "product this creative is meant to depict. For EACH of the "
        "fields listed below, judge whether the generated image "
        "faithfully preserves the real product's visual identity as "
        "shown in the reference photos - return exactly one "
        "field_checks entry per field below. field_name in your "
        "response must be ONLY the short field_name given in quotes "
        "below (e.g. \"silhouette\"), never a longer description. Set "
        "preserved=true or preserved=false and give a short reason "
        "explaining your judgment - this is strictly about whether the "
        "product's own physical identity was preserved, not about "
        "scene, lighting, or composition.\n\n"
        f"Fields to check:\n{field_lines}"
    )


def _resolve_product(db: Session, generated_image: GeneratedImage) -> Product | None:
    """
    GeneratedImage has no product_id of its own - resolved via the same
    Creative Specification -> Product Lock Profile -> Product chain the
    Prompt Compiler used to build the request in the first place, so
    Validation always judges against the exact product Generation was
    told to preserve.
    """
    creative_specification = db.get(CreativeSpecification, generated_image.creative_specification_id)
    if creative_specification is None:
        return None
    lock_profile = db.get(ProductLockProfile, creative_specification.product_lock_profile_id)
    if lock_profile is None:
        return None
    return db.get(Product, lock_profile.product_id)


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
            analysis_type=ANALYSIS_TYPE_IMAGE_VALIDATION,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=True,
        )

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
                    identity_result = vision_provider.analyze_creative(
                        image_bytes=[generated_image_bytes, *reference_bytes],
                        prompt_spec={"prompt": _build_identity_prompt(), "schema_name": "identity_validation"},
                        response_schema=IDENTITY_VALIDATION_SCHEMA,
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
                result = vision_provider.analyze_creative(
                    image_bytes=generated_image_bytes,
                    prompt_spec={"prompt": prompt, "schema_name": "image_validation"},
                    response_schema=IMAGE_VALIDATION_SCHEMA,
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

        return mark_succeeded(db, analysis_run)


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
        analysis_type=ANALYSIS_TYPE_IMAGE_VALIDATION,
        provider=vision_provider.provider,
        model_name=vision_provider.model,
        durable=True,
    )

    try:
        generated_image_bytes = Path(generated_image.file_path).read_bytes()
        reference_bytes = [Path(path).read_bytes() for path in reference_paths]
        identity_result = vision_provider.analyze_creative(
            image_bytes=[generated_image_bytes, *reference_bytes],
            prompt_spec={"prompt": _build_identity_prompt(), "schema_name": "identity_validation"},
            response_schema=IDENTITY_VALIDATION_SCHEMA,
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

    return mark_succeeded(db, analysis_run)
