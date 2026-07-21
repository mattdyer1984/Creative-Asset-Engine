"""
Product Isolation Stage (plan §6.3, §8A).

Requires Creative.product_id to already be set - fails gracefully if
not, rather than guessing which product to isolate for. Crops the
featured product out of the Creative's image using LLM-guided bounding
boxes, and saves each crop as a new ProductReferenceImage owned by the
Product (not this Creative) - see plan §7 for why.

Owns no CreativeBlueprint field directly (plan §6.3's documented
exception): its output feeds the next stage, Product Lock Profile.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.analysis_run import ANALYSIS_TYPE_PRODUCT_ISOLATION
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.product_reference_image import ProductReferenceImage
from app.stages.base import StageResult
from app.stages.execution import mark_failed, mark_succeeded, start_analysis_run
from app.storage import save_product_reference_image

ISOLATION_METHOD = "llm_bounding_box_v1"

# Small padding around each detected bounding box, as a fraction of the
# box's own width/height - keeps a bit of surrounding context rather than
# an exact crop to the model's (imprecise) reported edges.
CROP_PADDING_FRACTION = 0.05


class ProductIsolationStage:
    name = "product_isolation"

    def run(
        self, db: Session, creative: Creative, blueprint: CreativeBlueprint
    ) -> StageResult:
        if creative.product_id is None:
            return StageResult(
                succeeded=False,
                error="No product assigned to this creative - assign one before running Product Isolation.",
            )

        isolation_provider = default_registry.isolation()

        # Committed immediately as a durable "pending" record - if
        # anything below fails and we roll back, this row survives
        # (rollback only discards the *next* transaction, not one
        # already committed), so the failure is never silently lost.
        analysis_run = start_analysis_run(
            db,
            creative_id=creative.id,
            analysis_type=ANALYSIS_TYPE_PRODUCT_ISOLATION,
            provider=isolation_provider.provider,
            model_name=isolation_provider.model,
            durable=True,
        )

        try:
            image_bytes = Path(creative.stored_file_path).read_bytes()
            bounding_boxes = isolation_provider.isolate_product(image_bytes)
            if not bounding_boxes:
                raise ValueError("No product detected in the image")
            crops = _crop_bounding_boxes(image_bytes, bounding_boxes)

            # Create and persist every new reference image (DB row + file
            # on disk) BEFORE touching the previous "current" set - if
            # anything here fails (including a disk write), the except
            # block below rolls back this entire block, and the
            # previously-current reference images are never touched.
            new_reference_images = []
            for crop_bytes in crops:
                reference_image = ProductReferenceImage(
                    analysis_run_id=analysis_run.id,
                    product_id=creative.product_id,
                    source_creative_id=creative.id,
                    isolation_method=ISOLATION_METHOD,
                    file_path="",  # placeholder, set below once we have the row's id
                )
                db.add(reference_image)
                db.flush()

                stored_path = save_product_reference_image(
                    creative.product_id, reference_image.id, crop_bytes
                )
                reference_image.file_path = str(stored_path)
                new_reference_images.append(reference_image)

            # Only now, with every new reference image successfully
            # created and written to disk, flip the previous current ones
            # to not-current. Exclude the rows we just created: they
            # already default to is_current=True and would otherwise
            # match this same "current" filter and get incorrectly
            # flipped right back off.
            new_ids = [img.id for img in new_reference_images]
            db.query(ProductReferenceImage).filter(
                ProductReferenceImage.product_id == creative.product_id,
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
