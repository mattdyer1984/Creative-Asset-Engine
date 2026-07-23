"""
Unit tests for app.services.prompt_compiler (Phase 8.2 of the Generation
-> Validation proof of loop, see MIGRATION_PLAN.md). Plain dicts/model
construction only - no AI provider involved, matching the sub-phase's
own test strategy (the compiler's whole point is being provider-agnostic
and provider-free).
"""

from app.product_sources.base import ColorValue, ListValue, TextValue
from app.services.product_profile import ProductProfile, ProductProfileField
from app.services.prompt_compiler import compile_generation_request

_CREATIVE_SPECIFICATION = {
    "subject": "A single bottle of orange juice on a sunlit kitchen counter",
    "composition": "off-center product shot with negative space for text",
    "style_direction": "warm, natural morning light photography",
    "color_palette": ["warm orange", "cream", "soft green"],
    "lighting": "natural morning sunlight from the left",
    "camera_and_perspective": "eye-level, slight angle",
    "background_environment": "blurred kitchen counter with fruit",
    "mood": "fresh, energizing, morning routine",
    "text_overlays": [{"role": "headline", "content": "Start Fresh"}],
    "things_to_avoid": ["cluttered background", "artificial-looking lighting"],
    "aspect_ratio": "4:5",
    "extensions": "",
}


def _make_profile(fields: dict) -> ProductProfile:
    return ProductProfile(product_id="prod-1", fields=fields)


def test_immutable_constraints_come_only_from_immutable_fields():
    profile = _make_profile(
        {
            "brand": ProductProfileField(
                value=TextValue(text="Sunrise"),
                source_type="vision",
                source_id="lp-1",
                confidence=0.9,
                classification="immutable",
            ),
            "camera_angle": ProductProfileField(
                value=TextValue(text="eye-level"),
                source_type="vision",
                source_id="lp-1",
                confidence=0.9,
                classification="contextual",
            ),
        }
    )

    request = compile_generation_request(_CREATIVE_SPECIFICATION, profile)

    assert request.immutable_constraints == ["brand: Sunrise"]


def test_immutable_constraints_format_each_value_kind_readably():
    profile = _make_profile(
        {
            "color": ProductProfileField(
                value=ColorValue(label="orange", hex="#FFA500"),
                source_type="vision",
                source_id="lp-1",
                confidence=0.9,
                classification="immutable",
            ),
            "materials": ProductProfileField(
                value=ListValue(items=["glass", "plastic cap"]),
                source_type="vision",
                source_id="lp-1",
                confidence=0.9,
                classification="immutable",
            ),
        }
    )

    request = compile_generation_request(_CREATIVE_SPECIFICATION, profile)

    assert "color: orange (#FFA500)" in request.immutable_constraints
    assert "materials: glass, plastic cap" in request.immutable_constraints


def test_things_to_avoid_and_aspect_ratio_pass_through_unchanged():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _make_profile({}))

    assert request.things_to_avoid == ["cluttered background", "artificial-looking lighting"]
    assert request.aspect_ratio == "4:5"


def test_aspect_ratio_falls_back_to_platform_default_when_missing():
    spec_without_ratio = dict(_CREATIVE_SPECIFICATION)
    spec_without_ratio.pop("aspect_ratio")

    request = compile_generation_request(spec_without_ratio, _make_profile({}), platform="generic")

    assert request.aspect_ratio == "1:1"


def test_creative_intent_includes_descriptive_fields_and_color_palette_and_overlays():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _make_profile({}))

    assert "Subject: A single bottle of orange juice on a sunlit kitchen counter" in request.creative_intent
    assert "Composition: off-center product shot with negative space for text" in request.creative_intent
    assert "Color palette: warm orange, cream, soft green" in request.creative_intent
    assert "Text overlays: headline: Start Fresh" in request.creative_intent


def test_missing_optional_creative_specification_fields_are_skipped_not_blank():
    minimal = {
        "subject": "A bottle",
        "composition": "",
        "style_direction": None,
        "color_palette": [],
        "text_overlays": [],
        "things_to_avoid": [],
        "aspect_ratio": "1:1",
    }

    request = compile_generation_request(minimal, _make_profile({}))

    assert "Subject: A bottle" in request.creative_intent
    assert "Composition" not in request.creative_intent
    assert "Style" not in request.creative_intent
    assert "Color palette" not in request.creative_intent
    assert "Text overlays" not in request.creative_intent
