"""
Text-masked reference images (incident e3fbf713).

The delivered images carried two overlapping sets of captions: the model
copied the caption out of the reference image it was told to recreate,
and the Rendering Engine then composited its own on top. Every automated
check passed - identity, creative fidelity and photorealism say nothing
about duplicated text - so the defect reached the user unflagged.
"""

from io import BytesIO

from PIL import Image

from app.services.reference_masking import build_text_masked_image

OVERLAY_BOX = {"x_min": 0.1, "y_min": 0.1, "x_max": 0.6, "y_max": 0.2}


def _image(colour=(240, 238, 232), size=(400, 500)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG")
    return buffer.getvalue()


def _blocks(*surfaces):
    return [{"surface": s, "text": "x", "bounding_box": OVERLAY_BOX} for s in surfaces]


def test_overlay_text_is_masked():
    assert build_text_masked_image(_image(), _blocks("overlay")) is not None


def test_physical_product_text_is_never_masked():
    """
    Text printed on the product's own packaging is exactly what Product
    Lock exists to preserve - masking it would erase the branding the
    generator is required to reproduce.
    """
    assert build_text_masked_image(_image(), _blocks("physical")) is None


def test_a_mixed_slide_masks_only_the_overlay_blocks():
    result = build_text_masked_image(_image(), _blocks("physical", "overlay"))
    assert result is not None, "the overlay block should still be masked"


def test_no_ocr_blocks_means_no_masking():
    assert build_text_masked_image(_image(), []) is None
    assert build_text_masked_image(_image(), None) is None


def test_the_masked_region_actually_changes():
    """A mask that leaves the glyphs readable would not fix anything."""
    source = Image.new("RGB", (400, 500), (240, 238, 232))
    # A hard black bar standing in for text.
    for x in range(40, 240):
        for y in range(50, 100):
            source.putpixel((x, y), (0, 0, 0))
    buffer = BytesIO()
    source.save(buffer, format="JPEG")

    masked_bytes = build_text_masked_image(buffer.getvalue(), _blocks("overlay"))
    masked = Image.open(BytesIO(masked_bytes))
    # Sample the middle of the bar - it must no longer be black.
    r, g, b = masked.getpixel((140, 75))
    assert r > 100 and g > 100 and b > 100, "the text region is still dark"


def test_the_rest_of_the_image_is_preserved():
    """Masking must not touch the scene the generator has to recreate."""
    source = Image.new("RGB", (400, 500), (240, 238, 232))
    for x in range(300, 380):
        for y in range(400, 480):
            source.putpixel((x, y), (10, 90, 200))  # a "subject" far from the text
    buffer = BytesIO()
    source.save(buffer, format="JPEG")

    masked = Image.open(BytesIO(build_text_masked_image(buffer.getvalue(), _blocks("overlay"))))
    r, g, b = masked.getpixel((340, 440))
    assert b > 120 and r < 90, "the subject area should be untouched"


def test_refuses_to_mask_most_of_the_frame():
    """
    Boxes covering the whole frame mean the boxes are wrong, not that the
    slide is entirely text. Handing the model a blank canvas would be
    worse than handing it the original.
    """
    huge = [{"surface": "overlay", "bounding_box":
             {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 0.95}}]
    assert build_text_masked_image(_image(), huge) is None


def test_malformed_boxes_are_skipped_not_fatal():
    blocks = [
        {"surface": "overlay", "bounding_box": {"x_min": 0.9, "y_min": 0.1, "x_max": 0.2, "y_max": 0.2}},
        {"surface": "overlay", "bounding_box": {"x_min": "?", "y_min": None, "x_max": 1, "y_max": 1}},
    ]
    assert build_text_masked_image(_image(), blocks) is None


def test_unreadable_bytes_fall_back_rather_than_raising():
    """A masking failure must never cost a generation."""
    assert build_text_masked_image(b"not an image", _blocks("overlay")) is None
