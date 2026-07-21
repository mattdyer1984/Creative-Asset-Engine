"""
Product Lock Profile Stage (plan §6.3, §8B).

Generates the structured Product Lock Profile via the general-purpose
VisionAnalysisProvider, using the Creative's full original image (for
context - packaging, background, lighting) rather than only the cropped
reference image(s), and snapshots which ProductReferenceImage ids were
current at generation time into reference_image_ids_json.

Two small, deliberate adaptations from the plan's illustrative schema
(§8B), noted here rather than silently applied:
  1. "schema_version" is NOT part of the AI-generated JSON - it's a
     system-assigned property of the artifact row itself (via
     AnalysisArtifactMixin), not something the model should decide.
  2. "extensions" is a free-text string, not an open/arbitrary object -
     OpenAI's strict Structured Outputs mode requires every object in the
     schema to have a fully fixed, enumerated shape, so a truly
     freeform key-value bag isn't representable in strict mode.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run

PRODUCT_LOCK_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "product_category": {"type": "string"},
        "product_type": {"type": "string"},
        "shape_and_proportions": {"type": "string"},
        "packaging": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "closure": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["type", "closure", "notes"],
            "additionalProperties": False,
        },
        "materials": {"type": "array", "items": {"type": "string"}},
        "surface_finish": {"type": "string"},
        "colors": {
            "type": "object",
            "properties": {
                "primary": {"type": "array", "items": {"type": "string"}},
                "secondary": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["primary", "secondary"],
            "additionalProperties": False,
        },
        "branding": {
            "type": "object",
            "properties": {
                "brand_name": {"type": "string"},
                "logo_placement": {"type": "string"},
                "logo_description": {"type": "string"},
            },
            "required": ["brand_name", "logo_placement", "logo_description"],
            "additionalProperties": False,
        },
        "labels_and_text": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "location": {"type": "string"},
                    "font_style": {"type": "string"},
                },
                "required": ["text", "location", "font_style"],
                "additionalProperties": False,
            },
        },
        "distinguishing_features": {"type": "array", "items": {"type": "string"}},
        "viewing_angle": {"type": "string"},
        "perspective": {"type": "string"},
        "lighting_characteristics": {"type": "string"},
        "approximate_scale_in_frame": {"type": "string"},
        "immutable_characteristics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Visual traits that must NEVER change if this product is recreated.",
        },
        "extensions": {
            "type": "string",
            "description": "Any additional notes that don't fit the fields above.",
        },
    },
    "required": [
        "product_category",
        "product_type",
        "shape_and_proportions",
        "packaging",
        "materials",
        "surface_finish",
        "colors",
        "branding",
        "labels_and_text",
        "distinguishing_features",
        "viewing_angle",
        "perspective",
        "lighting_characteristics",
        "approximate_scale_in_frame",
        "immutable_characteristics",
        "extensions",
    ],
    "additionalProperties": False,
}

PRODUCT_LOCK_PROFILE_PROMPT = (
    "Analyze the featured product in this marketing image and produce a "
    "detailed, structured description covering its category, type, shape "
    "and proportions, packaging, materials, surface finish, colors, "
    "branding, any visible labels or printed text, distinguishing visual "
    "features, viewing angle, perspective, lighting characteristics, and "
    "its approximate scale within the frame. In immutable_characteristics, "
    "list the visual traits that must NEVER change if this exact product "
    "is recreated in a new marketing image."
)


class ProductLockProfileStage:
    name = "product_lock_profile"

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        if creative.product_id is None:
            return StageResult(
                succeeded=False,
                error="No product assigned to this creative - assign one before generating a Product Lock Profile.",
            )

        vision_provider = default_registry.vision()

        analysis_run = start_analysis_run(
            db,
            creative_id=creative.id,
            analysis_type=ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=False,
        )

        # Reads the Product's current reference images (plan §6.3) - if
        # Product Isolation hasn't produced any yet (e.g. this stage is
        # rerun standalone before isolation ever succeeded), we still
        # proceed using the Creative's own image; the snapshot below is
        # simply empty in that case, rather than treating it as a hard
        # prerequisite failure.
        current_reference_images = list(
            db.query(ProductReferenceImage).filter(
                ProductReferenceImage.product_id == creative.product_id,
                ProductReferenceImage.is_current.is_(True),
            )
        )

        try:
            image_bytes = Path(creative.stored_file_path).read_bytes()
            result = vision_provider.analyze_creative(
                image_bytes=image_bytes,
                prompt_spec={
                    "prompt": PRODUCT_LOCK_PROFILE_PROMPT,
                    "schema_name": "product_lock_profile",
                },
                response_schema=PRODUCT_LOCK_PROFILE_SCHEMA,
            )
        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=False)

        db.query(ProductLockProfile).filter(
            ProductLockProfile.product_id == creative.product_id,
            ProductLockProfile.is_current.is_(True),
        ).update({"is_current": False})

        profile = ProductLockProfile(
            analysis_run_id=analysis_run.id,
            product_id=creative.product_id,
            structured_json=json.dumps(result),
            reference_image_ids_json=json.dumps(
                [img.id for img in current_reference_images]
            ),
        )
        db.add(profile)
        db.flush()

        blueprint.current_product_lock_profile_id = profile.id
        return mark_succeeded(db, analysis_run)
