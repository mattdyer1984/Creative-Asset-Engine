"""
Product Isolation Stage (new pipeline) — Phase 2.4a of the Slideshow/
Slide migration.

Parallel equivalent of app.stages.product_isolation_stage.
ProductIsolationStage. Behavior is intentionally identical to the old
stage for Phase 2 - still requires exactly one product to be associated
with the slide, still fails if the provider detects zero products.

The one real difference: "is a product assigned" is answered by
querying for a current ProductAppearance on the slide, replacing
Creative.product_id's single direct FK - see Phase 2.4's design note in
the migration roadmap.

Phase 6 (multi per-slide product detection, see MIGRATION_PLAN.md) made
assigning *multiple* products to one slide possible (via the new
POST .../slides/{id}/products endpoint), but deliberately does NOT make
this stage isolate each one automatically - isolate_product takes a
whole slide image and a generic, non-targeted prompt, with no way to
tell it *which* assigned product to focus on. Calling it once per
product would just return the same detection twice, mislabeled under
two different product_ids - silently wrong data, worse than an honest
failure. A slide with 2+ current appearances fails clearly instead (see
_MULTI_PRODUCT_ERROR below) - real product-targeted isolation is future
work, logged in MIGRATION_PLAN.md, not guessed at here.

Real-world-diagnosed widening (Generate All, see MIGRATION_PLAN.md): now
loops over every slide in the slideshow, not just the primary one -
mirrors app.slideshow_stages.ocr_stage.SlideOCRStage's own Phase 7.1
precedent, which this module previously, deliberately deferred (see that
Stage's own docstring) until something actually needed per-slide
isolation for a non-primary slide. See SlideProductIsolationStage.run's
own docstring for the exact per-slide skip/fail semantics.

_crop_bounding_boxes is deliberately duplicated from the old stage
rather than shared, to keep this sub-phase from touching any file the
old, still-live pipeline depends on (the whole point of building this
package in parallel) - see Phase 2.7, where the old stage is deleted and
this becomes the only copy.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_PRODUCT_ISOLATION
from app.models.product_reference_image import ProductReferenceImage
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.concurrency import run_concurrently
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run
from app.storage import save_product_reference_image

ISOLATION_METHOD = "llm_bounding_box_v1"

# Small padding around each detected bounding box, as a fraction of the
# box's own width/height - keeps a bit of surrounding context rather than
# an exact crop to the model's (imprecise) reported edges.
CROP_PADDING_FRACTION = 0.05


_MULTI_PRODUCT_ERROR = (
    "Multiple products assigned to this slide - automated per-product isolation isn't "
    "implemented yet. Each product's isolation must currently be generated from a slide "
    "where it's the only one assigned."
)


class SlideProductIsolationStage:
    name = "product_isolation"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        """
        Real-world-diagnosed fix (Generate All, see MIGRATION_PLAN.md):
        widened from `slideshow.primary_slide` only to every slide in
        `slideshow.slides`, mirroring `SlideOCRStage`'s own Phase 7.1
        precedent exactly - the same widening this stage's own module
        docstring once explicitly deferred as "a real cost/design
        tradeoff not required" until something actually needed it.
        Generate All is that something: a non-primary slide's own
        assigned product needs its own isolated reference images before
        that slide can build a Reference Library or generate at all.

        A slide with no current product appearance is skipped, not
        failed - a completely normal, expected state for a slide that
        hasn't been assigned a product yet (most non-primary slides,
        most of the time). The *primary* slide having no product is
        still a hard failure, exactly as before - that's a real setup
        problem, not a transient one. A slide with 2+ appearances (the
        still-unsupported multi-product-per-slide case) still fails the
        whole stage loudly, same as it always has for the primary slide -
        silently skipping a real, actionable problem would be worse than
        an honest failure, unlike "nothing assigned yet."

        Real-world-diagnosed speed fix (see MIGRATION_PLAN.md): the
        actual `isolate_product` provider call for every eligible slide
        now runs concurrently (app.slideshow_stages.concurrency), not
        one slide at a time - the skip/fail eligibility checks above
        still run first, sequentially, exactly as before, so an early
        return for "no product on the primary slide" or "2+ products on
        one slide" never even starts any provider calls. Every other DB
        write (start_analysis_run, ProductReferenceImage rows,
        mark_succeeded/mark_failed) still happens afterward, on this
        single thread, in original slide order - only the slow network
        call itself was moved off the sequential path.
        """
        primary_slide = slideshow.primary_slide
        isolation_provider = default_registry.isolation()
        result: StageResult = StageResult(succeeded=True)

        eligible: list[tuple[Slide, str]] = []
        for slide in slideshow.slides:
            current_appearances = slide.current_product_appearances
            if not current_appearances:
                if slide.id == primary_slide.id:
                    return StageResult(
                        succeeded=False,
                        error="No product assigned to this slide - assign one before running Product Isolation.",
                    )
                continue
            distinct_product_ids = {a.product_id for a in current_appearances}
            if len(distinct_product_ids) > 1:
                return StageResult(succeeded=False, error=_MULTI_PRODUCT_ERROR)
            eligible.append((slide, current_appearances[0].product_id))

        def _isolate(entry: tuple[Slide, str]) -> tuple[bytes, list[dict]]:
            slide, _product_id = entry
            image_bytes = Path(slide.stored_file_path).read_bytes()
            bounding_boxes = isolation_provider.isolate_product(image_bytes)
            if not bounding_boxes:
                raise ValueError("No product detected in the image")
            return image_bytes, bounding_boxes

        isolation_results = run_concurrently(eligible, _isolate)

        for index, (slide, product_id) in enumerate(eligible):
            # Committed immediately as a durable "pending" record - same
            # reasoning as the old stage: if anything below fails and we
            # roll back, this row survives, so the failure is never silently
            # lost.
            analysis_run = start_analysis_run(
                db,
                slide_id=slide.id,
                analysis_type=ANALYSIS_TYPE_PRODUCT_ISOLATION,
                provider=isolation_provider.provider,
                model_name=isolation_provider.model,
                durable=True,
            )

            try:
                outcome = isolation_results[index]
                if isinstance(outcome, Exception):
                    raise outcome
                image_bytes, bounding_boxes = outcome
                crops = _crop_bounding_boxes(image_bytes, bounding_boxes)

                new_reference_images = []
                for crop_bytes in crops:
                    reference_image = ProductReferenceImage(
                        analysis_run_id=analysis_run.id,
                        product_id=product_id,
                        source_slide_id=slide.id,
                        isolation_method=ISOLATION_METHOD,
                        file_path="",  # placeholder, set below once we have the row's id
                    )
                    db.add(reference_image)
                    db.flush()

                    stored_path = save_product_reference_image(
                        product_id, reference_image.id, crop_bytes
                    )
                    reference_image.file_path = str(stored_path)
                    new_reference_images.append(reference_image)

                new_ids = [img.id for img in new_reference_images]
                db.query(ProductReferenceImage).filter(
                    ProductReferenceImage.product_id == product_id,
                    ProductReferenceImage.is_current.is_(True),
                    ProductReferenceImage.id.notin_(new_ids),
                ).update({"is_current": False}, synchronize_session=False)

            except Exception as exc:
                return mark_failed(db, analysis_run, exc, rollback=True)

            result = mark_succeeded(db, analysis_run)

        return result


def _crop_bounding_boxes(image_bytes: bytes, bounding_boxes: list[dict]) -> list[bytes]:
    image = Image.open(BytesIO(image_bytes))
    image = image.convert("RGB")
    width, height = image.size

    crops = []
    for box in bounding_boxes:
        box_width_frac = box["x_max"] - box["x_min"]
        box_height_frac = box["y_max"] - box["y_min"]
        pad_x = box_width_frac * CROP_PADDING_FRACTION
        pad_y = box_height_frac * CROP_PADDING_FRACTION

        left = max(0.0, box["x_min"] - pad_x) * width
        top = max(0.0, box["y_min"] - pad_y) * height
        right = min(1.0, box["x_max"] + pad_x) * width
        bottom = min(1.0, box["y_max"] + pad_y) * height

        cropped = image.crop((int(left), int(top), int(right), int(bottom)))
        buffer = BytesIO()
        cropped.save(buffer, format="JPEG")
        crops.append(buffer.getvalue())

    return crops
