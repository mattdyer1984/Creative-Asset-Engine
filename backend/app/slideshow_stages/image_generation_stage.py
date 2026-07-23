"""
Image Generation Stage — Phase 8.3 of the Generation -> Validation proof
of loop; rewritten in Phase 9.3 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §6) to run
Reference Selection before compiling, instead of the canonical Product
Profile - the product is no longer described in text at all, the
selected reference images are the only source of product identity a
generation call carries.

`SlideshowAnalysisStage`-shaped (`name`, `run(db, slideshow) ->
StageResult`) for consistency with every other stage, but deliberately
NOT added to `SLIDESHOW_STAGE_PIPELINE` - image generation costs real
money per call in a way every existing stage doesn't as sharply, and
"Analyze / Re-run All" must not silently start generating images. This
stage is only ever run via its own dedicated, explicitly-triggered
endpoint (POST .../slides/{slide_id}/generate-image in
app.routers.slideshows).

Scoped to `slideshow.primary_slide` - same convention every stage before
Phase 6/7.1 used, and matches the Phase 8 architecture direction's
explicit "generate one slide first, not an entire slideshow" scope
boundary. The route validates the given slide_id actually is the
primary slide before calling this stage, rather than silently ignoring
a caller-supplied slide_id that isn't - honest about the real
limitation, same discipline Product Isolation/Lock Profile use for
rejecting multi-product slides outright.

Reuses resolve_primary_appearance from creative_specification_stage
(the same "which product is this artifact about" resolution a Creative
Specification was already built around) - no new resolution logic here.

Create-then-link ordering for GenerationReferenceSet, per ADR §3/§6:
Reference Selection persists the Set (and its member rows) before
generation runs, since the prompt needs the selected image paths first;
once generation succeeds, this stage links the Set back to the
GeneratedImage it fed (GenerationReferenceSet.generated_image_id) and
records the same relationship the other direction
(GeneratedImage.generation_reference_set_id) - both sides of the FK are
written here, deliberately, so either can be queried directly without a
join.
"""

from sqlalchemy.orm import Session

from app import storage
from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_GENERATED_IMAGE
from app.models.creative_specification import CreativeSpecification
from app.models.generated_image import GeneratedImage
from app.models.generation_reference_set_image import GenerationReferenceSetImage
from app.models.product import Product
from app.models.product_reference_image import ProductReferenceImage
from app.models.slideshow import Slideshow
from app.services.prompt_compiler import compile_generation_request
from app.services.reference_selection import select_reference_images
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.creative_specification_stage import resolve_primary_appearance
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run


class SlideImageGenerationStage:
    name = "generated_image"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.primary_slide

        if slideshow.current_creative_specification_id is None:
            return StageResult(
                succeeded=False,
                error="No Creative Specification available yet - run that stage first.",
            )
        creative_specification = db.get(
            CreativeSpecification, slideshow.current_creative_specification_id
        )
        if creative_specification is None:
            return StageResult(
                succeeded=False,
                error="Creative Specification referenced by the Slideshow no longer exists.",
            )

        current_appearance = resolve_primary_appearance(slide.current_product_appearances)
        if current_appearance is None:
            return StageResult(
                succeeded=False,
                error="No product assigned to this slide yet - assign one first.",
            )
        product = db.get(Product, current_appearance.product_id)
        if product is None:
            return StageResult(
                succeeded=False,
                error="Product referenced by the Slide's current appearance no longer exists.",
            )

        image_provider = default_registry.image_generation()

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

        reference_image_paths = _resolve_reference_image_paths(db, generation_reference_set.id)

        analysis_run = start_analysis_run(
            db,
            slide_id=slide.id,
            analysis_type=ANALYSIS_TYPE_GENERATED_IMAGE,
            provider=image_provider.provider,
            model_name=image_provider.model,
            durable=True,
        )

        try:
            request = compile_generation_request(
                creative_specification.structured_json, reference_image_paths
            )
            result = image_provider.generate_image(request)

            db.query(GeneratedImage).filter(
                GeneratedImage.slide_id == slide.id,
                GeneratedImage.is_current.is_(True),
            ).update({"is_current": False})

            generated_image = GeneratedImage(
                analysis_run_id=analysis_run.id,
                slideshow_id=slideshow.id,
                slide_id=slide.id,
                creative_specification_id=creative_specification.id,
                generation_reference_set_id=generation_reference_set.id,
                provider=result.provider,
                model_name=result.model,
                prompt_used=result.prompt_used,
                seed=result.seed,
                generation_time_seconds=result.generation_time_seconds,
                file_path="",
            )
            db.add(generated_image)
            db.flush()

            generation_reference_set.generated_image_id = generated_image.id

            saved_path = storage.save_generated_image(
                slide.id, generated_image.id, result.image_bytes
            )
            generated_image.file_path = str(saved_path)
            db.flush()

        except Exception as exc:
            return mark_failed(db, analysis_run, exc, rollback=True)

        return mark_succeeded(db, analysis_run)


def _resolve_reference_image_paths(db: Session, generation_reference_set_id: str) -> list[str]:
    rows = (
        db.query(GenerationReferenceSetImage, ProductReferenceImage)
        .join(
            ProductReferenceImage,
            ProductReferenceImage.id == GenerationReferenceSetImage.product_reference_image_id,
        )
        .filter(GenerationReferenceSetImage.generation_reference_set_id == generation_reference_set_id)
        .order_by(GenerationReferenceSetImage.rank)
        .all()
    )
    return [reference_image.file_path for _, reference_image in rows]
