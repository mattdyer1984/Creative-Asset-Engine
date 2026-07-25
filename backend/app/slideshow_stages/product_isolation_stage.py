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

import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_PRODUCT_ISOLATION
from app.models.product_appearance import ProductAppearance
from app.models.product_reference_image import ProductReferenceImage
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.slideshow_stages.concurrency import run_concurrently
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run
from app.storage import save_product_reference_image
from app.prompts import analysis as _analysis_prompts

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
        hasn't been assigned a product yet. A slide with 2+ appearances
        (the still-unsupported multi-product-per-slide case) still
        fails the whole stage loudly - silently skipping a real,
        actionable problem would be worse than an honest failure, unlike
        "nothing assigned yet."

        Real-world-diagnosed fix (see MIGRATION_PLAN.md): earlier
        revisions of this Stage treated the *primary* slide specially -
        hard-failing if it had no product assigned, or if the provider
        detected nothing there - on the assumption that the primary
        slide (slides[0]) always shows the product. Real TikTok
        slideshows regularly lead with a text-only "hook" slide and show
        the product on a later slide instead - that assumption was
        simply wrong, confirmed live. There is nothing structurally
        special about the primary slide's *product content*; every
        slide is treated identically now:

        - No appearance assigned: skip (see above).
        - Appearance assigned but the provider detects zero bounding
          boxes: a narrative/story slide genuinely without the product
          in frame - retract that slide's own ProductAppearance
          (is_current=False, same soft-delete semantics as the DELETE
          .../products/{appearance_id} endpoint) so every downstream
          stage's existing "no current appearance -> skip" logic picks
          it up for free, and move on to the next slide.

        The real, still-necessary failure condition is checked once, at
        the end, across the whole slideshow: if NOT ONE eligible slide
        ends up with a detected product, there is nothing to build a
        Canonical Reference Library from at all, and that's a genuine,
        actionable setup problem worth failing loudly on.

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
        isolation_provider = default_registry.isolation()
        result: StageResult = StageResult(succeeded=True)

        eligible: list[tuple[Slide, str]] = []
        for slide in slideshow.slides:
            current_appearances = slide.current_product_appearances
            if not current_appearances:
                continue
            distinct_product_ids = {a.product_id for a in current_appearances}
            if len(distinct_product_ids) > 1:
                return StageResult(succeeded=False, error=_MULTI_PRODUCT_ERROR)
            eligible.append((slide, current_appearances[0].product_id))

        if not eligible:
            return StageResult(
                succeeded=False,
                error="No product assigned to any slide - assign one before running Product Isolation.",
            )

        def _isolate(entry: tuple[Slide, str]):
            slide, _product_id = entry
            image_bytes = Path(slide.stored_file_path).read_bytes()
            usage: dict = {}
            start = time.perf_counter()
            bounding_boxes = isolation_provider.isolate_product(image_bytes, usage_sink=usage)
            provider_call_ms = (time.perf_counter() - start) * 1000
            # Real-world-diagnosed fix (see MIGRATION_PLAN.md): zero boxes
            # is no longer raised as an exception here - it's a
            # legitimate outcome (a story/narrative slide genuinely
            # doesn't show the product), not a provider error. The
            # persist loop below decides what "zero boxes on this slide"
            # means for the slideshow overall, since that's a business
            # rule, not a detection-call concern.
            return image_bytes, bounding_boxes, provider_call_ms, usage

        isolation_results = run_concurrently(eligible, _isolate)
        any_product_detected = False

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
                image_bytes, bounding_boxes, provider_call_ms, usage = outcome

                if not bounding_boxes:
                    # Genuinely no product in frame (a narrative/story
                    # slide, or a mistaken assignment) - retract it so
                    # every downstream stage's existing "no current
                    # appearance -> skip" logic picks this slide up for
                    # free, and move on rather than aborting the whole
                    # slideshow's analysis. Whether this is actually a
                    # problem for the slideshow overall is decided once,
                    # after this loop, by any_product_detected.
                    db.query(ProductAppearance).filter(
                        ProductAppearance.slide_id == slide.id,
                        ProductAppearance.product_id == product_id,
                        ProductAppearance.is_current.is_(True),
                    ).update({"is_current": False}, synchronize_session=False)
                    result = mark_succeeded(
                        db,
                        analysis_run,
                        provider_call_ms=provider_call_ms,
                        usage=usage,
                        prompt=_analysis_prompts.PRODUCT_ISOLATION,
                    )
                    continue

                any_product_detected = True
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

            result = mark_succeeded(
                db,
                analysis_run,
                provider_call_ms=provider_call_ms,
                usage=usage,
                prompt=_analysis_prompts.PRODUCT_ISOLATION,
            )

        if not any_product_detected:
            # Every eligible slide's ProductAppearance has now been
            # retracted above - a real, actionable problem (nothing to
            # build a Canonical Reference Library from), not silently
            # swallowed just because no single slide was singled out as
            # "the" one required to show it.
            return StageResult(
                succeeded=False,
                error=(
                    "No product could be detected in any slide - the assigned product "
                    "doesn't appear to be visible in any of this slideshow's images. Check "
                    "the product assignment, or add a slide that actually shows it."
                ),
            )

        return result


def _crop_bounding_boxes(image_bytes: bytes, bounding_boxes: list[dict]) -> list[bytes]:
    image = Image.open(BytesIO(image_bytes))
    image = image.convert("RGB")
    width, height = image.size

    crops = []
    for box in bounding_boxes:
        # Real bug found live (see MIGRATION_PLAN.md): the isolation
        # model occasionally returns an inverted box (y_min > y_max, or
        # x_min > x_max) - a real, observed anomaly (also seen during
        # the Tier 4.1 downscaling benchmark), not a hypothetical edge
        # case. Uncorrected, this makes the padded top/bottom (or
        # left/right) computed below cross each other, and PIL's own
        # crop() raises "Coordinate 'lower' is less than 'upper'" -
        # normalizing min/max here guarantees a valid box regardless of
        # which order the model returned the coordinates in; a no-op
        # for the ordinary, already-correctly-ordered case.
        x_min = min(box["x_min"], box["x_max"])
        x_max = max(box["x_min"], box["x_max"])
        y_min = min(box["y_min"], box["y_max"])
        y_max = max(box["y_min"], box["y_max"])

        box_width_frac = x_max - x_min
        box_height_frac = y_max - y_min
        pad_x = box_width_frac * CROP_PADDING_FRACTION
        pad_y = box_height_frac * CROP_PADDING_FRACTION

        left = max(0.0, x_min - pad_x) * width
        top = max(0.0, y_min - pad_y) * height
        right = min(1.0, x_max + pad_x) * width
        bottom = min(1.0, y_max + pad_y) * height

        cropped = image.crop((int(left), int(top), int(right), int(bottom)))
        buffer = BytesIO()
        cropped.save(buffer, format="JPEG")
        crops.append(buffer.getvalue())

    return crops
