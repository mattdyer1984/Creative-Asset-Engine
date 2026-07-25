"""
Text-masked reference images.

**The defect this fixes.** On a story slide the reference image handed to
the generator IS the original slide, and the prompt says "recreate its
scene, composition and mood". The original slide has the marketing
caption burned into it. The prompt also says, emphatically, "Do not
render ANY text of any kind" - but a picture outvotes a sentence: the
model reproduced "Your upper back feels rounded" in the same serif, the
same red/black split, the same position. The Rendering Engine then
composited its own overlay on top, and the delivered image carried two
overlapping sets of captions. Every automated check passed it: identity,
creative fidelity and photorealism all say nothing about duplicated text.

So the fix is not another instruction. It is to stop showing the model
the text in the first place.

**Only OVERLAY text is masked.** OCR already classifies every block's
`surface` as `physical` (printed, moulded or displayed on a real object
the camera photographed) or `overlay` (added digitally afterwards - a
caption, a meme line, a watermark). Masking physical text would erase
the product's own branding, which Product Lock exists to preserve, so
that distinction is load-bearing rather than incidental.

Masking is best-effort: if anything goes wrong the original reference is
used, exactly as before. A masking failure must never cost a generation.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

SURFACE_OVERLAY = "overlay"

# OCR boxes sit tight against the glyphs; a few percent of padding covers
# antialiased edges and descenders that would otherwise survive as a
# readable ghost the model can still copy.
_BOX_PADDING = 0.012

# Below this the "mask" would cover most of the frame, which means the
# boxes are wrong rather than that the slide is all text. Fall back to
# the unmasked original rather than handing the model a blank canvas.
_MAX_MASKED_FRACTION = 0.6


def build_text_masked_image(image_bytes: bytes, ocr_blocks: list[dict]) -> bytes | None:
    """
    Returns `image_bytes` with every overlay-text region painted out, or
    None when there is nothing to mask or masking would be unsafe.

    Each region is filled with the median colour of a ring sampled just
    OUTSIDE it, then the edges are softened. Sampling outside matters: an
    earlier version blurred the region itself, which works for thin
    strokes on a light background but leaves a bold headline as a dark
    smudge the model still reads as "something belongs here". The ring
    carries only the surrounding background, so the patch reads as empty
    space rather than as a deliberate graphic element.
    """
    overlay_boxes = [
        block.get("bounding_box")
        for block in ocr_blocks or []
        if block.get("surface") == SURFACE_OVERLAY and block.get("bounding_box")
    ]
    if not overlay_boxes:
        return None

    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
            width, height = image.size

            fill_layer = image.copy()
            fill_draw = ImageDraw.Draw(fill_layer)
            mask = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(mask)
            masked_area = 0
            for box in overlay_boxes:
                try:
                    x_min = max(0.0, float(box["x_min"]) - _BOX_PADDING)
                    y_min = max(0.0, float(box["y_min"]) - _BOX_PADDING)
                    x_max = min(1.0, float(box["x_max"]) + _BOX_PADDING)
                    y_max = min(1.0, float(box["y_max"]) + _BOX_PADDING)
                except (KeyError, TypeError, ValueError):
                    continue
                if x_max <= x_min or y_max <= y_min:
                    continue
                left, top = int(x_min * width), int(y_min * height)
                right, bottom = int(x_max * width), int(y_max * height)
                fill_draw.rectangle(
                    [left, top, right, bottom],
                    fill=_surrounding_colour(image, left, top, right, bottom),
                )
                draw.rectangle([left, top, right, bottom], fill=255)
                masked_area += (right - left) * (bottom - top)

            if masked_area == 0:
                return None
            if masked_area / float(width * height) > _MAX_MASKED_FRACTION:
                logger.warning(
                    "Refusing to mask %.0f%% of the reference image - the OCR boxes look wrong",
                    100 * masked_area / float(width * height),
                )
                return None

            # Soften the mask edges so patches blend instead of showing
            # rectangles the model would treat as content.
            mask = mask.filter(ImageFilter.GaussianBlur(radius=6))
            image.paste(fill_layer.filter(ImageFilter.GaussianBlur(radius=8)), mask=mask)

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=92)
            return buffer.getvalue()
    except Exception:
        logger.exception("Could not build a text-masked reference image")
        return None


def masked_reference_path(
    original_path: str, ocr_blocks: list[dict], destination_dir: Path
) -> str:
    """
    Writes a masked copy next to the caller's working directory and
    returns its path, or the original path when masking did not apply.

    Callers pass the returned path straight to the generator, so the
    fallback is always a usable reference rather than an error.
    """
    try:
        source = Path(original_path)
        masked = build_text_masked_image(source.read_bytes(), ocr_blocks)
        if masked is None:
            return original_path
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{source.stem}.text-masked.jpg"
        destination.write_bytes(masked)
        return str(destination)
    except Exception:
        logger.exception("Falling back to the unmasked reference for %s", original_path)
        return original_path


def _surrounding_colour(
    image: Image.Image, left: int, top: int, right: int, bottom: int
) -> tuple[int, int, int]:
    """
    The median colour of a thin ring just outside the box.

    Median rather than mean so a few dark pixels bleeding in from an
    adjacent element cannot drag the fill away from the real background.
    """
    width, height = image.size
    margin = max(4, (right - left) // 20, (bottom - top) // 20)
    samples: list[tuple[int, int, int]] = []

    for x in range(max(0, left - margin), min(width, right + margin), 3):
        for y in (max(0, top - margin), min(height - 1, bottom + margin - 1)):
            samples.append(image.getpixel((x, y)))
    for y in range(max(0, top - margin), min(height, bottom + margin), 3):
        for x in (max(0, left - margin), min(width - 1, right + margin - 1)):
            samples.append(image.getpixel((x, y)))

    if not samples:
        return (255, 255, 255)
    return tuple(
        sorted(channel)[len(channel) // 2]
        for channel in zip(*samples, strict=False)
    )
