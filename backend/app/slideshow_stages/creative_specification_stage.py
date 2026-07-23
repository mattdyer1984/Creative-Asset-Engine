"""
Creative Specification Stage (new pipeline) — Phase 2.4e of the
Slideshow/Slide migration, the final stage in the original 6-stage
pipeline (Narrative Structure, Phase 7.2, was inserted before this one
in the actual run order - see pipeline.py).

Renamed from RecreationPromptStage in Phase 8.1 of the Generation ->
Validation proof of loop (see MIGRATION_PLAN.md) - see
app.models.creative_specification's docstring for why.

Parallel equivalent of app.stages.recreation_prompt_stage.
RecreationPromptStage (old pipeline, removed). Slideshow-scoped (owns
Slideshow.current_creative_specification_id, writes
CreativeSpecification.slideshow_id) - same reasoning as Marketing
Analysis (Phase 2.4d).

One real difference from the old stage, beyond entity plumbing: finding
"the current Product Lock Profile" is no longer a single pointer
dereference (the old CreativeBlueprint.current_product_lock_profile_id,
deliberately removed - see Phase 2.4b's docstring on why). Instead:
current ProductAppearance on the slide -> product_id -> current
ProductLockProfile for that product_id. Two lookups instead of one, but
each is scoped to its own single source of truth
(ProductAppearance.is_current, ProductLockProfile.is_current), so
nothing can disagree with itself the way the old pointer/is_current pair
could.

CREATIVE_SPECIFICATION_AI_SCHEMA duplicated from the old stage, same
self-containment reasoning as the other new stages.

Phase 6 (multi per-slide product detection, see MIGRATION_PLAN.md) made
assigning multiple products to one slide possible. Unlike Product
Isolation/Lock Profile (Phase 6.2), which reject 2+-product slides
outright because their provider calls have no way to target a specific
product, a creative specification is inherently single-subject - it
describes one product being recreated. Rather than fail a multi-product
slide entirely, this stage resolves a single *primary* product to write
the specification around: the appearance with prominence == "primary" if
exactly one exists, otherwise the earliest-created current appearance
(deterministic, not an arbitrary query-order pick). This is a scope
boundary, not a full solution - a slide with several equally-important
products still only gets one creative specification, built around
whichever product resolves as primary. Broader multi-product support is
future work, not attempted here.
"""

from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_CREATIVE_SPECIFICATION
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.creative_specification import CreativeSpecification
from app.models.product_appearance import ProductAppearance
from app.models.product_lock_profile import ProductLockProfile
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


def resolve_primary_appearance(
    current_appearances: list[ProductAppearance],
) -> ProductAppearance | None:
    """
    Picks the single ProductAppearance a creative specification should be
    built around, per the docstring above: prefer the one explicitly
    marked prominence == "primary" (ties broken by earliest-created);
    otherwise fall back to the earliest-created current appearance.

    Not underscore-prefixed (unlike its original name in this file) -
    Phase 8.3's Image Generation Stage reuses this exact resolution logic
    to find the same primary product a slide's Creative Specification was
    built around, rather than duplicating it.
    """
    if not current_appearances:
        return None
    primary_marked = [a for a in current_appearances if a.prominence == "primary"]
    candidates = primary_marked or current_appearances
    return min(candidates, key=lambda a: (a.created_at, a.id))

CREATIVE_SPECIFICATION_AI_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "composition": {"type": "string"},
        "style_direction": {"type": "string"},
        "color_palette": {"type": "array", "items": {"type": "string"}},
        "lighting": {"type": "string"},
        "camera_and_perspective": {"type": "string"},
        "background_environment": {"type": "string"},
        "mood": {"type": "string"},
        "text_overlays": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "headline, subhead, or cta",
                    },
                    "content": {"type": "string"},
                },
                "required": ["role", "content"],
                "additionalProperties": False,
            },
        },
        "things_to_avoid": {"type": "array", "items": {"type": "string"}},
        "aspect_ratio": {"type": "string"},
        "extensions": {
            "type": "string",
            "description": "Any additional notes that don't fit the fields above.",
        },
    },
    "required": [
        "subject",
        "composition",
        "style_direction",
        "color_palette",
        "lighting",
        "camera_and_perspective",
        "background_environment",
        "mood",
        "text_overlays",
        "things_to_avoid",
        "aspect_ratio",
        "extensions",
    ],
    "additionalProperties": False,
}


class SlideCreativeSpecificationStage:
    name = "creative_specification"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.primary_slide

        current_appearance = resolve_primary_appearance(slide.current_product_appearances)
        lock_profile = None
        if current_appearance is not None:
            lock_profile = (
                db.query(ProductLockProfile)
                .filter(
                    ProductLockProfile.product_id == current_appearance.product_id,
                    ProductLockProfile.is_current.is_(True),
                )
                .first()
            )
        if lock_profile is None:
            return StageResult(
                succeeded=False,
                error="No Product Lock Profile available yet - run that stage first.",
            )

        if slide.current_creative_fingerprint_id is None:
            return StageResult(
                succeeded=False,
                error="No Creative Fingerprint available yet - run that stage first.",
            )
        fingerprint = db.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
        if fingerprint is None:
            return StageResult(
                succeeded=False,
                error="Creative Fingerprint referenced by the Slide no longer exists.",
            )

        prompt_provider = default_registry.prompt_generation()

        analysis_run = start_analysis_run(
            db,
            slideshow_id=slideshow.id,
            analysis_type=ANALYSIS_TYPE_CREATIVE_SPECIFICATION,
            provider=prompt_provider.provider,
            model_name=prompt_provider.model,
            durable=True,
        )

        try:
            lock_profile_data = lock_profile.structured_json
            fingerprint_data = fingerprint.structured_json

            ai_result = prompt_provider.generate_creative_specification(
                lock_profile=lock_profile_data,
                fingerprint=fingerprint_data,
                response_schema=CREATIVE_SPECIFICATION_AI_SCHEMA,
            )

            # Assembled directly from known facts, never asked of the AI.
            final_structured = dict(ai_result)
            final_structured["product_lock_reference"] = {
                "product_lock_profile_id": lock_profile.id,
                "reference_image_ids": lock_profile.reference_image_ids_json,
                "immutable_characteristics": lock_profile_data.get(
                    "immutable_characteristics", []
                ),
            }

            db.query(CreativeSpecification).filter(
                CreativeSpecification.slideshow_id == slideshow.id,
                CreativeSpecification.is_current.is_(True),
            ).update({"is_current": False})

            creative_specification = CreativeSpecification(
                analysis_run_id=analysis_run.id,
                slideshow_id=slideshow.id,
                product_lock_profile_id=lock_profile.id,
                creative_fingerprint_id=fingerprint.id,
                structured_json=final_structured,
            )
            db.add(creative_specification)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        slideshow.current_creative_specification_id = creative_specification.id
        return mark_succeeded(db, analysis_run)
