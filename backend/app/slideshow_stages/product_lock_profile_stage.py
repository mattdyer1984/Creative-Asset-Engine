"""
Product Lock Profile Stage (new pipeline) — Phase 2.4b of the
Slideshow/Slide migration.

Parallel equivalent of app.stages.product_lock_profile_stage.
ProductLockProfileStage. "Is a product assigned" is answered via a
current ProductAppearance on the slide, replacing Creative.product_id.

Deliberately does NOT set any current_product_lock_profile_id pointer on
Slide or Slideshow, unlike the old CreativeBlueprint, which had exactly
that pointer - and that pointer is exactly what produced the
product-scoped-currency bug characterized in
tests/test_product_scoped_currency_characterization.py (two Creatives
sharing a Product could show each other's reference images, and a lock
profile's own pointer could disagree with its own is_current flag).
ProductLockProfile's currency is determined purely by is_current scoped
to product_id - the single source of truth, with nothing else able to
get out of sync with it. This is a deliberate fix carried into the new
model from the start, not an oversight.

PRODUCT_LOCK_PROFILE_SCHEMA/PROMPT are duplicated from the old stage
rather than imported from it, same reasoning as
_crop_bounding_boxes in the new Product Isolation stage: keeps this
package fully self-contained so Phase 2.7 can delete the old stage files
without this package needing to change.

Phase 6 (multi per-slide product detection, see MIGRATION_PLAN.md) made
assigning multiple products to one slide possible, but deliberately does
NOT make this stage profile each one automatically - the vision call
below takes a whole slide image and a generic "the featured product"
prompt, with no way to target a specific assigned product. A slide with
2+ current appearances fails clearly (see _MULTI_PRODUCT_ERROR below)
instead of silently producing the same profile twice under two different
product_ids - real product-targeted profiling is future work, logged in
MIGRATION_PLAN.md, not guessed at here.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
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
            "description": (
                "Only text that is physically printed, embossed, or molded onto the "
                "product's own packaging, container, or body - the same text would "
                "still be there if the product were photographed on its own, with no "
                "caption, sticker, or watermark added. Do NOT include text that was "
                "overlaid onto this photo by whoever took or posted it (social-media "
                "captions, meme-style commentary, price stickers/shelf tags added by a "
                "retailer, watermarks) - that text is about this photo, not about the "
                "product, and does not belong here even if it's clearly visible."
            ),
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

_MULTI_PRODUCT_ERROR = (
    "Multiple products assigned to this slide - automated per-product profiling isn't "
    "implemented yet. Each product's Lock Profile must currently be generated from a slide "
    "where it's the only one assigned."
)

PRODUCT_LOCK_PROFILE_PROMPT = (
    "Analyze the featured product in this marketing image and produce a "
    "detailed, structured description covering its category, type, shape "
    "and proportions, packaging, materials, surface finish, colors, "
    "branding, any visible labels or printed text, distinguishing visual "
    "features, viewing angle, perspective, lighting characteristics, and "
    "its approximate scale within the frame. For labels_and_text, only "
    "include text that is actually printed, embossed, or molded onto the "
    "product's own packaging or body - never text overlaid onto this "
    "photo afterward, such as a social-media caption, meme-style "
    "commentary, a retailer's price sticker or shelf tag, or a watermark. "
    "If you're unsure whether a piece of text is part of the product "
    "itself or was overlaid onto the photo, leave it out. In "
    "immutable_characteristics, list the visual traits that must NEVER "
    "change if this exact product is recreated in a new marketing image."
)


class SlideProductLockProfileStage:
    name = "product_lock_profile"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.primary_slide

        current_appearances = slide.current_product_appearances
        if not current_appearances:
            return StageResult(
                succeeded=False,
                error="No product assigned to this slide - assign one before generating a Product Lock Profile.",
            )
        distinct_product_ids = {a.product_id for a in current_appearances}
        if len(distinct_product_ids) > 1:
            return StageResult(succeeded=False, error=_MULTI_PRODUCT_ERROR)
        product_id = current_appearances[0].product_id

        # Real-world-driven cost/quality change (see MIGRATION_PLAN.md) -
        # explicit provider_name="gemini" override: this is one of only
        # two vision_analysis tasks moved to Gemini (Creative Fingerprint
        # is the other), a narrower scope the user chose over moving
        # every vision_analysis task at once.
        vision_provider = default_registry.vision(provider_name="gemini")

        analysis_run = start_analysis_run(
            db,
            slide_id=slide.id,
            analysis_type=ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE,
            provider=vision_provider.provider,
            model_name=vision_provider.model,
            durable=False,
        )

        # Reads the Product's current reference images - if Product
        # Isolation hasn't produced any yet (e.g. this stage is rerun
        # standalone before isolation ever succeeded), we still proceed
        # using the Slide's own image; the snapshot below is simply
        # empty in that case, rather than a hard prerequisite failure.
        current_reference_images = list(
            db.query(ProductReferenceImage).filter(
                ProductReferenceImage.product_id == product_id,
                ProductReferenceImage.is_current.is_(True),
            )
        )

        try:
            image_bytes = Path(slide.stored_file_path).read_bytes()
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
            ProductLockProfile.product_id == product_id,
            ProductLockProfile.is_current.is_(True),
        ).update({"is_current": False})

        profile = ProductLockProfile(
            analysis_run_id=analysis_run.id,
            product_id=product_id,
            structured_json=result,
            reference_image_ids_json=[img.id for img in current_reference_images],
        )
        db.add(profile)
        db.flush()

        return mark_succeeded(db, analysis_run)
