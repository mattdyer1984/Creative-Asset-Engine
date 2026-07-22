"""
Product Isolation Stage (new pipeline) — Phase 2.4a of the Slideshow/
Slide migration.

Parallel equivalent of app.stages.product_isolation_stage.
ProductIsolationStage. Behavior is intentionally identical to the old
stage for Phase 2 - still requires exactly one product to be associated
with the slide, still fails if the provider detects zero products.
Genuinely optional/multi-product detection is Phase 5, not this one.

The one real difference: "is a product assigned" is answered by
querying for a current ProductAppearance on the slide, replacing
Creative.product_id's single direct FK - see Phase 2.4's design note in
the migration roadmap.

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
from app.models.product_appearance import ProductAppearance
from app.models.product_reference_image import ProductReferenceImage
from app.models.slideshow import Slideshow
from app.slideshow_stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run
from app.storage import save_product_reference_image

ISOLATION_METHOD = "llm_bounding_box_v1"

# Small padding around each detected bounding box, as a fraction of the
# box's own width/height - keeps a bit of surrounding context rather than
# an exact crop to the model's (imprecise) reported edges.
CROP_PADDING_FRACTION = 0.05


class SlideProductIsolationStage:
    name = "product_isolation"

    def run(self, db: Session, slideshow: Slideshow) -> StageResult:
        slide = slideshow.primary_slide

        current_appearance = (
            db.query(ProductAppearance)
            .filter(
                ProductAppearance.slide_id == slide.id,
                ProductAppearance.is_current.is_(True),
            )
            .first()
        )
        if current_appearance is None:
            return StageResult(
                succeeded=False,
                error="No product assigned to this slide - assign one before running Product Isolation.",
            )
        product_id = current_appearance.product_id

        isolation_provider = default_registry.isolation()

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
            image_bytes = Path(slide.stored_file_path).read_bytes()
            bounding_boxes = isolation_provider.isolate_product(image_bytes)
            if not bounding_boxes:
                raise ValueError("No product detected in the image")
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

        return mark_succeeded(db, analysis_run)


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
