"""
Unit tests for app.services.rendering_engine (Phase 10.8 of AI Creative
Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext"
§15). Real Pillow compositing (no fakes - there's no provider to fake,
this module is pure image manipulation); visual quality itself was
confirmed via a real, live feasibility spike (see this phase's report
in MIGRATION_PLAN.md), not re-asserted pixel-by-pixel here - these
tests check the mechanical contract (pass-through, real output bytes,
no crash across both render styles).
"""

from io import BytesIO

from PIL import Image

from app.services.rendering_engine import _load_default_typeface, _resolve_y, render_final_output


def _source_image_bytes(size=(800, 800), color=(120, 130, 140)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_no_text_assets_is_a_byte_identical_pass_through():
    source = _source_image_bytes()
    assert render_final_output(source, []) == source


def test_scrim_style_text_asset_produces_a_valid_larger_image():
    source = _source_image_bytes()
    text_asset = {
        "wording": "SMELL LIKE YOU MEAN IT",
        "hierarchy": "headline",
        "semantic_role": "hook",
        "positioning": {"x": 0.05, "y": 0.05, "width": 0.8},
        "styling": {"size_class": "large", "weight": "bold", "render_style": "scrim"},
    }

    result_bytes = render_final_output(source, [text_asset])

    assert result_bytes != source
    result_image = Image.open(BytesIO(result_bytes))
    assert result_image.size == (800, 800)
    assert result_image.format == "PNG"


def test_badge_style_text_asset_produces_a_valid_image():
    source = _source_image_bytes()
    text_asset = {
        "wording": "SHOP NOW",
        "hierarchy": "cta",
        "semantic_role": "cta",
        "positioning": {"x": 0.05, "y": 0.85, "width": 0.25},
        "styling": {"size_class": "medium", "weight": "bold", "render_style": "badge"},
    }

    result_bytes = render_final_output(source, [text_asset])

    assert result_bytes != source
    result_image = Image.open(BytesIO(result_bytes))
    assert result_image.size == (800, 800)


def test_multiple_text_assets_all_render_without_crashing():
    source = _source_image_bytes()
    text_assets = [
        {
            "wording": "SMELL LIKE YOU MEAN IT",
            "hierarchy": "headline",
            "semantic_role": "hook",
            "positioning": {"x": 0.05, "y": 0.05, "width": 0.8},
            "styling": {"size_class": "large", "weight": "bold", "render_style": "scrim"},
        },
        {
            "wording": "Now 30% off",
            "hierarchy": "subhead",
            "semantic_role": "proof",
            "positioning": {"x": 0.05, "y": 0.25, "width": 0.6},
            "styling": {"size_class": "medium", "weight": "regular", "render_style": "scrim"},
        },
        {
            "wording": "SHOP NOW",
            "hierarchy": "cta",
            "semantic_role": "cta",
            "positioning": {"x": 0.05, "y": 0.85, "width": 0.25},
            "styling": {"size_class": "medium", "weight": "bold", "render_style": "badge"},
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
        "styling": {"size_class": "medium", "weight": "bold", "render_style": "badge"},
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
    Real bug found live-verifying this fix: four shelf price tags meant
    to sit side-by-side (different x, near-identical y) were all being
    cascaded downward by an earlier, x-blind version of this function.
    A box directly beside another (no x overlap) must not be pushed
    down just because their y ranges are close.
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
        "styling": {"size_class": "large", "weight": "bold", "render_style": "scrim"},
    }
    cta_same_position = {
        "wording": "SHOP NOW",
        "hierarchy": "cta",
        "semantic_role": "cta",
        "positioning": {"x": 0.05, "y": 0.05, "width": 0.25},
        "styling": {"size_class": "medium", "weight": "bold", "render_style": "badge"},
    }

    combined = Image.open(BytesIO(render_final_output(source, [headline, cta_same_position]))).convert("RGB")
    headline_only = Image.open(BytesIO(render_final_output(source, [headline]))).convert("RGB")

    # If the CTA badge had been drawn at its raw, un-adjusted y=0.05
    # (identical to the headline's own start), it would sit on top of
    # the wrapped headline's scrim - the combined render's top region
    # would then differ from a headline-only render in a way that looks
    # like overwriting rather than stacking. Instead, assert the
    # headline's own scrim area (its first line) renders identically
    # whether or not the CTA is also present - proof the CTA was pushed
    # down below it, not drawn over it.
    top_band = (0, 0, combined.width, int(combined.height * 0.08))
    assert list(combined.crop(top_band).getdata()) == list(headline_only.crop(top_band).getdata())
