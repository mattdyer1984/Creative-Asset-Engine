"""
Image Generation Stage — Phase 8.3 of the Generation -> Validation proof
of loop (see MIGRATION_PLAN.md).

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
Specification was already built around) and assemble_product_profile
(Phase 5.5's canonical Product Profile) - no new resolution logic here.
"""

from sqlalchemy.orm import Session

from app import storage
from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_GENERATED_IMAGE
from app.models.creative_specification import CreativeSpecification
from app.models.generated_image import GeneratedImage
from app.models.product import Product
from app.models.slideshow import Slideshow
from app.services.product_profile import assemble_product_profile
from app.services.prompt_compiler import compile_generation_request
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

        analysis_run = start_analysis_run(
            db,
            slide_id=slide.id,
            analysis_type=ANALYSIS_TYPE_GENERATED_IMAGE,
            provider=image_provider.provider,
            model_name=image_provider.model,
            durable=True,
        )

        try:
            product_profile = assemble_product_profile(db, product)
            request = compile_generation_request(
                creative_specification.structured_json, product_profile
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
            return mark_failed(db, analysis_run, exc, rollback=True)

        return mark_succeeded(db, analysis_run)
