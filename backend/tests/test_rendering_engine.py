"""
Unit tests for app.services.rendering_engine (Phase 10.8 of AI Creative
Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext"
§15). Real Pillow compositing (no fakes - there's no provider to fake,
this module is pure image manipulation); visual quality itself was
confirmed via a real, live feasibility spike (see this phase's report
in MIGRATION_PLAN.md), not re-asserted pixel-by-pixel for every detail
here - but the style redesign (centered, stroked, no background box,
see MIGRATION_PLAN.md) is a real, user-directed behavior change with
concrete pixel-level guarantees, so a few tests below do inspect real
pixels rather than only checking "doesn't crash."
"""

from io import BytesIO

from PIL import Image, ImageChops

from app.services.rendering_engine import _load_default_typeface, _resolve_y, render_final_output

_BACKGROUND_COLOR = (120, 130, 140)


def _source_image_bytes(size=(800, 800), color=_BACKGROUND_COLOR) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _non_background_bbox(image: Image.Image, background_color=_BACKGROUND_COLOR):
    """The bounding box of every pixel that differs from a flat background of this color - i.e. the rendered text."""
    flat = Image.new("RGB", image.size, color=background_color)
    diff = ImageChops.difference(image.convert("RGB"), flat)
    return diff.getbbox()


def test_no_text_assets_is_a_byte_identical_pass_through():
    source = _source_image_bytes()
    assert render_final_output(source, []) == source


def test_text_asset_produces_a_valid_larger_image():
    source = _source_image_bytes()
    text_asset = {
        "wording": "SMELL LIKE YOU MEAN IT",
        "hierarchy": "headline",
        "semantic_role": "hook",
        "positioning": {"x": 0.05, "y": 0.05, "width": 0.8},
        "styling": {"size_class": "large"},
    }

    result_bytes = render_final_output(source, [text_asset])

    assert result_bytes != source
    result_image = Image.open(BytesIO(result_bytes))
    assert result_image.size == (800, 800)
    assert result_image.format == "PNG"


def test_multiple_text_assets_all_render_without_crashing():
    source = _source_image_bytes()
    text_assets = [
        {
            "wording": "SMELL LIKE YOU MEAN IT",
            "hierarchy": "headline",
            "semantic_role": "hook",
            "positioning": {"x": 0.05, "y": 0.05, "width": 0.8},
            "styling": {"size_class": "large"},
        },
        {
            "wording": "Now 30% off",
            "hierarchy": "subhead",
            "semantic_role": "proof",
            "positioning": {"x": 0.05, "y": 0.25, "width": 0.6},
            "styling": {"size_class": "medium"},
        },
        {
            "wording": "SHOP NOW",
            "hierarchy": "cta",
            "semantic_role": "cta",
            "positioning": {"x": 0.05, "y": 0.85, "width": 0.25},
            "styling": {"size_class": "medium"},
        },
    ]

    result_bytes = render_final_output(source, text_assets)
    result_image = Image.open(BytesIO(result_bytes))
    assert result_image.size == (800, 800)


def test_handles_a_non_square_aspect_ratio():
    source = _source_image_bytes(size=(1024, 1280))
    text_asset = {
        "wording": "SHOP NOW",
        "hierarchy": "cta",
        "semantic_role": "cta",
        "positioning": {"x": 0.05, "y": 0.9, "width": 0.25},
        "styling": {"size_class": "medium"},
    }

    result_bytes = render_final_output(source, [text_asset])
    result_image = Image.open(BytesIO(result_bytes))
    assert result_image.size == (1024, 1280)


# --- real-world-diagnosed fixes (see MIGRATION_PLAN.md) ---


def test_default_typeface_has_a_real_pound_sterling_glyph():
    """
    Real bug: Pillow's bundled ImageFont.load_default() has no glyph for
    £ at all (confirmed via a live render test showing a blank tofu box,
    not a wrapping/encoding issue) - _load_default_typeface must resolve
    to a font that actually renders it, wherever one is available.
    """
    font = _load_default_typeface(60)
    mask = font.getmask("£")
    assert mask.getbbox() is not None  # a real glyph occupies pixels; a missing one renders empty


def test_resolve_y_pushes_down_when_a_horizontally_overlapping_box_is_below_it():
    placed = [(0, 100, 100)]  # a box spanning x=0-100, bottom edge at y=100
    assert _resolve_y(y=50, x_start=20, x_end=80, placed=placed, margin=5) == 105


def test_resolve_y_leaves_position_unchanged_when_there_is_no_vertical_overlap():
    placed = [(0, 100, 100)]
    assert _resolve_y(y=200, x_start=20, x_end=80, placed=placed, margin=5) == 200


def test_resolve_y_leaves_the_first_box_unchanged():
    assert _resolve_y(y=50, x_start=0, x_end=100, placed=[], margin=5) == 50


def test_resolve_y_ignores_boxes_that_do_not_overlap_horizontally():
    """
    Real bug found live-verifying an earlier version of this fix: several
    boxes meant to sit side-by-side (different x, near-identical y) were
    all being cascaded downward by an x-blind version of this function.
    A box directly beside another (no x overlap) must not be pushed down
    just because their y ranges are close.
    """
    placed = [(0, 100, 200)]  # a box spanning x=0-100, bottom edge at y=200
    assert _resolve_y(y=50, x_start=150, x_end=250, placed=placed, margin=5) == 50


def test_two_assets_at_the_same_original_position_do_not_collide():
    """
    Real bug: a headline that wraps to multiple lines can grow taller
    than its own original single-line bounding box, overlapping
    whatever sits right below it. Two assets pinned to the identical
    original y must still render without the second overwriting the
    first - proven by rendering them separately at the same nominal
    position and confirming the combined render isn't simply the
    second one drawn on top of the first, i.e. the first is still
    visible after compositing.
    """
    source = _source_image_bytes(size=(900, 900), color=(255, 255, 255))
    headline = {
        "wording": "SMELL LIKE YOU MEAN IT EVERY SINGLE DAY OF THE YEAR",
        "hierarchy": "headline",
        "semantic_role": "hook",
        "positioning": {"x": 0.05, "y": 0.05, "width": 0.3},  # narrow width forces multi-line wrapping
        "styling": {"size_class": "large"},
    }
    cta_same_position = {
        "wording": "SHOP NOW",
        "hierarchy": "cta",
        "semantic_role": "cta",
        "positioning": {"x": 0.05, "y": 0.05, "width": 0.25},
        "styling": {"size_class": "medium"},
    }

    combined = Image.open(BytesIO(render_final_output(source, [headline, cta_same_position]))).convert("RGB")
    headline_only = Image.open(BytesIO(render_final_output(source, [headline]))).convert("RGB")

    # If the CTA had been drawn at its raw, un-adjusted y=0.05 (identical
    # to the headline's own start), it would sit on top of the wrapped
    # headline's own first line - the combined render's top region would
    # then differ from a headline-only render in a way that looks like
    # overwriting rather than stacking. Instead, assert the headline's
    # own first-line area renders identically whether or not the CTA is
    # also present - proof the CTA was pushed down below it, not drawn
    # over it.
    top_band = (0, 0, combined.width, int(combined.height * 0.08))
    assert list(combined.crop(top_band).getdata()) == list(headline_only.crop(top_band).getdata())


# --- style redesign, real-world-diagnosed and user-directed (see MIGRATION_PLAN.md) ---


def test_text_is_horizontally_centered_on_the_image_not_left_justified():
    """
    Real user request: text must always be centered, never left-
    justified against wherever the original slide's OCR happened to
    find it (e.g. positioning.x near the left edge, as in this fixture).
    """
    source = _source_image_bytes(size=(800, 800))
    text_asset = {
        "wording": "SHOP NOW",
        "hierarchy": "cta",
        "semantic_role": "cta",
        "positioning": {"x": 0.02, "y": 0.5, "width": 0.1},  # positioned near the left edge
        "styling": {"size_class": "medium"},
    }

    result_image = Image.open(BytesIO(render_final_output(source, [text_asset])))
    bbox = _non_background_bbox(result_image)
    assert bbox is not None

    text_center_x = (bbox[0] + bbox[2]) / 2
    image_center_x = result_image.width / 2
    assert abs(text_center_x - image_center_x) < result_image.width * 0.02


def test_no_background_box_is_drawn_behind_the_text():
    """
    Real user request: no black (or any other) background box - a
    real, direct pixel check that the area immediately beside the
    rendered glyphs (where the old scrim/badge rectangle used to fill
    a wide band) is untouched, still the original background color.
    """
    source = _source_image_bytes(size=(800, 800))
    text_asset = {
        "wording": "GO",  # short text - leaves plenty of untouched space on either side to sample
        "hierarchy": "cta",
        "semantic_role": "cta",
        "positioning": {"x": 0.4, "y": 0.5, "width": 0.1},
        "styling": {"size_class": "medium"},
    }

    result_image = Image.open(BytesIO(render_final_output(source, [text_asset]))).convert("RGB")
    bbox = _non_background_bbox(result_image)
    assert bbox is not None

    # Sample well outside the glyphs' own bounding box, at the same
    # row - a filled background rectangle would have covered this;
    # the new style must leave it exactly the original color.
    sample_y = (bbox[1] + bbox[3]) // 2
    sample_x = max(bbox[0] - 40, 0)
    assert result_image.getpixel((sample_x, sample_y)) == _BACKGROUND_COLOR


def test_text_is_drawn_with_a_visible_stroke_outline():
    """Real user request: "a little bit of stroke" - both the white fill and the black outline must be present."""
    source = _source_image_bytes(size=(800, 800))
    text_asset = {
        "wording": "SHOP NOW",
        "hierarchy": "cta",
        "semantic_role": "cta",
        "positioning": {"x": 0.3, "y": 0.5, "width": 0.3},
        "styling": {"size_class": "large"},
    }

    result_image = Image.open(BytesIO(render_final_output(source, [text_asset]))).convert("RGB")
    colors = {pixel for pixel in result_image.getdata()}

    assert (255, 255, 255) in colors  # white fill
    assert (0, 0, 0) in colors  # black stroke
