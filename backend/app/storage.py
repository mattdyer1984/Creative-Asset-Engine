"""
Local filesystem storage for creative and product assets.

Layout is keyed by owning entity, not by a shared parent - matches the
architecture's "storage keyed by the entity that owns it" pattern (plan
§2, §7):

    storage/creatives/<creative_id>/original<ext>
    storage/products/<product_id>/reference_<reference_image_id><ext>
    storage/slides/<slide_id>/generated_<generated_image_id><ext>
"""

from pathlib import Path

from app.config import settings


def save_creative_original(creative_id: str, original_filename: str, content: bytes) -> Path:
    creative_dir = settings.storage_dir / "creatives" / creative_id
    creative_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(original_filename).suffix or ".bin"
    dest = creative_dir / f"original{suffix}"
    dest.write_bytes(content)
    return dest


def save_product_reference_image(
    product_id: str, reference_image_id: str, content: bytes, suffix: str = ".jpg"
) -> Path:
    """
    Reference images are owned by Product (plan §7), not by the Creative
    they were cropped from - hence storage/products/, not nested under
    storage/creatives/.
    """
    product_dir = settings.storage_dir / "products" / product_id
    product_dir.mkdir(parents=True, exist_ok=True)

    dest = product_dir / f"reference_{reference_image_id}{suffix}"
    dest.write_bytes(content)
    return dest


def save_generated_image(
    slide_id: str, generated_image_id: str, content: bytes, suffix: str = ".png"
) -> Path:
    """
    Generated images are owned by the Slide they were generated for
    (Phase 8.3 of the Generation -> Validation proof of loop, see
    MIGRATION_PLAN.md) - not by Slideshow, matching the "one slide
    first" scope of this phase and the same per-owning-entity layout
    pattern as save_product_reference_image above.
    """
    slide_dir = settings.storage_dir / "slides" / slide_id
    slide_dir.mkdir(parents=True, exist_ok=True)

    dest = slide_dir / f"generated_{generated_image_id}{suffix}"
    dest.write_bytes(content)
    return dest


def save_final_output(slide_id: str, final_output_id: str, content: bytes, suffix: str = ".png") -> Path:
    """
    Phase 10.8 of AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
    §15) - same per-Slide-owning-entity layout as save_generated_image
    above, a sibling file rather than overwriting the source
    GeneratedImage's own file (that file stays the untouched, raw
    model output - see FinalOutput's own docstring for why these are
    deliberately separate artifacts).
    """
    slide_dir = settings.storage_dir / "slides" / slide_id
    slide_dir.mkdir(parents=True, exist_ok=True)

    dest = slide_dir / f"final_{final_output_id}{suffix}"
    dest.write_bytes(content)
    return dest
