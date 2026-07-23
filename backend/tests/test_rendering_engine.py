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

from app.services.rendering_engine import render_final_output


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
