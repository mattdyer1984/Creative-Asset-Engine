"""
Unit tests for app.services.prompt_compiler (Phase 8.2 of the Generation
-> Validation proof of loop; rewritten in Phase 9.3 of Product Lock v2,
see MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §6). Plain
dicts/lists only - no AI provider involved, matching the sub-phase's
own test strategy (the compiler's whole point is being provider-agnostic,
provider-free, and now also product-description-free).
"""

import pytest

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

_REFERENCE_PATHS = ["/data/storage/products/prod-1/ref-1.jpg", "/data/storage/products/prod-1/ref-2.jpg"]


def test_reference_image_paths_is_a_hard_prerequisite():
    with pytest.raises(ValueError, match="at least one reference image"):
        compile_generation_request(_CREATIVE_SPECIFICATION, [])


def test_reference_image_paths_pass_through_unchanged():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)

    assert request.reference_image_paths == _REFERENCE_PATHS


def test_things_to_avoid_and_aspect_ratio_pass_through_unchanged():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)

    assert request.things_to_avoid == ["cluttered background", "artificial-looking lighting"]
    assert request.aspect_ratio == "4:5"


def test_aspect_ratio_falls_back_to_platform_default_when_missing():
    spec_without_ratio = dict(_CREATIVE_SPECIFICATION)
    spec_without_ratio.pop("aspect_ratio")

    request = compile_generation_request(spec_without_ratio, _REFERENCE_PATHS, platform="generic")

    assert request.aspect_ratio == "1:1"


def test_creative_intent_excludes_subject_but_includes_scene_fields_color_palette_and_overlays():
    """
    Phase 9.3's core behavior change: "subject" (the one field that
    describes the product itself) must never appear in creative_intent -
    the reference images are the only source of product identity now.
    Every scene/composition field is still included unchanged.
    """
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)

    assert "orange juice" not in request.creative_intent
    assert "Subject:" not in request.creative_intent
    assert "Composition: off-center product shot with negative space for text" in request.creative_intent
    assert "Style: warm, natural morning light photography" in request.creative_intent
    assert "Lighting: natural morning sunlight from the left" in request.creative_intent
    assert "Camera & perspective: eye-level, slight angle" in request.creative_intent
    assert "Background: blurred kitchen counter with fruit" in request.creative_intent
    assert "Mood: fresh, energizing, morning routine" in request.creative_intent
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

    request = compile_generation_request(minimal, _REFERENCE_PATHS)

    # Phase 10.8's unconditional photorealism directive means
    # creative_intent is never truly blank anymore - only the optional
    # scene fields themselves are skipped when absent.
    assert request.creative_intent == (
        "This must look like a real photograph, not an illustration, painting, "
        "3D render, or cartoon - avoid stylized, plastic-looking, or "
        "artificial textures."
    )
    assert "Composition" not in request.creative_intent
    assert "Style" not in request.creative_intent
    assert "Color palette" not in request.creative_intent
    assert "Text overlays" not in request.creative_intent


# --- Phase 10.7 of AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
# §12's "Bundle Composition" addendum) -------------------------------


def test_no_bundle_instruction_when_bundle_members_is_none():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "BUNDLE" not in request.creative_intent


def test_bundle_instruction_lists_each_member_role_and_its_reference_range():
    bundle_members = [
        {"role_in_scene": "hero perfume bottle", "image_count": 2},
        {"role_in_scene": "background mug", "image_count": 1},
    ]
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS + ["/data/storage/products/prod-2/ref-1.jpg"],
        bundle_members=bundle_members,
    )

    assert "BUNDLE" in request.creative_intent
    assert "hero perfume bottle: shown in reference images 1-2" in request.creative_intent
    assert "background mug: shown in reference image 3" in request.creative_intent


def test_bundle_instruction_comes_before_the_ordinary_scene_fields():
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS,
        bundle_members=[{"role_in_scene": "hero", "image_count": 2}],
    )
    assert request.creative_intent.index("BUNDLE") < request.creative_intent.index("Composition:")


# --- Phase 10.8 of AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
# §9/§15) -----------------------------------------------------------


def test_photorealism_directive_is_unconditional():
    """Every compiled prompt gets the photorealism directive, regardless of suppress_overlay_text."""
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "real photograph" in request.creative_intent

    suppressed = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, suppress_overlay_text=True
    )
    assert "real photograph" in suppressed.creative_intent


def test_default_behavior_still_renders_text_overlays_unchanged():
    """suppress_overlay_text defaults to False - a real, deliberate backward-compatibility choice."""
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "Text overlays: headline: Start Fresh" in request.creative_intent
    assert "Do not render any marketing" not in request.creative_intent


def test_suppress_overlay_text_removes_the_render_instruction_and_adds_the_clean_area_instruction():
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, suppress_overlay_text=True
    )
    assert "Text overlays:" not in request.creative_intent
    assert "Do not render any marketing" in request.creative_intent


# --- branding_text (real-world-diagnosed prompting fix, see MIGRATION_PLAN.md) ---


def test_no_branding_text_instruction_when_branding_text_is_none_or_empty():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "packaging/label" not in request.creative_intent

    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS, branding_text=[])
    assert "packaging/label" not in request.creative_intent


def test_branding_text_is_quoted_verbatim_in_creative_intent():
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, branding_text=["BELLA VITA", "Net Wt 8 oz"]
    )

    assert 'reproduce it verbatim' in request.creative_intent
    assert '"BELLA VITA"' in request.creative_intent
    assert '"Net Wt 8 oz"' in request.creative_intent


def test_bundle_instruction_includes_each_members_own_branding_text():
    bundle_members = [
        {"role_in_scene": "hero perfume bottle", "image_count": 2, "branding_text": ["BELLA VITA"]},
        {"role_in_scene": "background mug", "image_count": 1},
    ]
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS + ["/data/storage/products/prod-2/ref-1.jpg"],
        bundle_members=bundle_members,
    )

    lines = request.creative_intent.splitlines()
    hero_line = next(line for line in lines if line.startswith("- hero perfume bottle"))
    mug_line = next(line for line in lines if line.startswith("- background mug"))
    assert hero_line == (
        '- hero perfume bottle: shown in reference images 1-2. Its own packaging/label '
        'shows this exact text - reproduce it verbatim: "BELLA VITA".'
    )
    # the second member has no branding_text - its line must not gain the extra sentence
    assert mug_line == "- background mug: shown in reference image 3"
