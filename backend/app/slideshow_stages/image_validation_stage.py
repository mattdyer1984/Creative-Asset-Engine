"""
Image Validation Stage — Phase 8.4 of the Generation -> Validation proof
of loop (see MIGRATION_PLAN.md).

Reuses VisionAnalysisProvider unchanged - no new AI capability needed,
per the architecture direction ("Validation - reuses
VisionAnalysisProvider, no new provider"). Lists every immutable-
classified field on the canonical Product Profile (Phase 5.5) and asks
the vision model to judge, per field, whether the generated image
preserves it - `passed` is computed here from the returned per-field
judgments, never asked of the AI as a bare boolean, matching this
codebase's standing rule that anything derivable from known facts is
assembled directly (same discipline
SlideCreativeSpecificationStage/SlideshowNarrativeStructureStage already
follow for their own assembled fields).

Deliberate signature difference from every SlideshowAnalysisStage:
`run(db, generated_image)`, not `run(db, slideshow)`. Validation targets
one specific GeneratedImage instance (there can be several over time for
one slide), never "whichever is current for the slideshow" - the
Protocol shape that fits every other stage genuinely doesn't fit this
one. Deliberately NOT added to SLIDESHOW_STAGE_PIPELINE either way - a
real vision-analysis call per validation, explicitly triggered via its
own endpoint, not automatic.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_IMAGE_VALIDATION
from app.models.creative_specification import CreativeSpecification
from app.models.generated_image import GeneratedImage
from app.models.image_validation_result import ImageValidationResult
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.services.product_profile import assemble_product_profile
from app.services.prompt_compiler import format_attribute_value
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

        vision_provider = default_registry.vision()

        analysis_run = start_analysis_run(
            db,
            analysis_type=ANALYSIS_TYPE_IMAGE_VALIDATION,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=True,
        )

        try:
            image_bytes = Path(generated_image.file_path).read_bytes()
            prompt = _build_prompt(
                [(name, format_attribute_value(value)) for name, value in immutable_fields]
            )
            result = vision_provider.analyze_creative(
                image_bytes=image_bytes,
                prompt_spec={"prompt": prompt, "schema_name": "image_validation"},
                response_schema=IMAGE_VALIDATION_SCHEMA,
            )

            field_checks = result["field_checks"]
            passed = bool(field_checks) and all(check["preserved"] for check in field_checks)

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
                overall_explanation=result["overall_explanation"],
            )
            db.add(validation_result)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        return mark_succeeded(db, analysis_run)
