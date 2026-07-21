"""
Local filesystem storage for creative and product assets.

Layout is keyed by owning entity, not by a shared parent - matches the
architecture's "storage keyed by the entity that owns it" pattern (plan
§2, §7):

    storage/creatives/<creative_id>/original<ext>
    storage/products/<product_id>/reference_<reference_image_id><ext>
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
