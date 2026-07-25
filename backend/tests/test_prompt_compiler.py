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


def test_things_to_avoid_passes_through_unchanged():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)

    assert request.things_to_avoid == ["cluttered background", "artificial-looking lighting"]


def test_aspect_ratio_is_always_3_4_regardless_of_the_creative_specification():
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): aspect_ratio used
    to pass through whatever the Creative Specification's own AI stage
    inferred (typically "9:16 vertical social media frame", matching
    the source slide) - once actually posted to TikTok, the app's own
    UI covers a real, fixed strip of a 9:16 frame. 3:4 is now a flat,
    unconditional product policy, not a per-creative judgment call or a
    per-platform lookup.
    """
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert request.aspect_ratio == "3:4"

    spec_without_ratio = dict(_CREATIVE_SPECIFICATION)
    spec_without_ratio.pop("aspect_ratio")
    request = compile_generation_request(spec_without_ratio, _REFERENCE_PATHS)
    assert request.aspect_ratio == "3:4"


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
        "Match the visual medium and level of stylisation of the source "
        "creative exactly as described above - do not shift it toward a "
        "different medium."
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


def test_a_rendering_directive_is_always_present_but_style_aware():
    """
    There is ALWAYS a rendering-mode instruction, regardless of
    suppress_overlay_text - but it is no longer unconditionally
    photographic. This test used to assert "real photograph" appeared on
    every prompt; that was the defect. With no style classification the
    compiler now states the source-faithful instruction, which is safe
    for any medium.
    """
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "Match the visual medium" in request.creative_intent

    suppressed = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, suppress_overlay_text=True
    )
    assert "Match the visual medium" in suppressed.creative_intent


def test_a_photographic_source_still_gets_the_realism_directive():
    """The realism demand is kept - scoped to sources that are photographic."""
    from app.services.source_style import classify_source_style

    request = compile_generation_request(
        _CREATIVE_SPECIFICATION,
        _REFERENCE_PATHS,
        source_style=classify_source_style(
            {"visual_style": "UGC candid photo", "graphic_style": "Photographic with text overlay"}
        ),
    )
    assert "real photograph" in request.creative_intent


def test_an_illustrated_source_never_gets_the_realism_directive():
    """The incident: an illustrated slide told to become a photograph."""
    from app.services.source_style import classify_source_style

    request = compile_generation_request(
        _CREATIVE_SPECIFICATION,
        _REFERENCE_PATHS,
        source_style=classify_source_style(
            {"visual_style": "Illustrative", "graphic_style": "Digital illustration, hand-drawn"}
        ),
    )
    assert "real photograph" not in request.creative_intent
    assert "remain an ILLUSTRATION" in request.creative_intent


def test_default_behavior_still_renders_text_overlays_unchanged():
    """suppress_overlay_text defaults to False - a real, deliberate backward-compatibility choice."""
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "Text overlays: headline: Start Fresh" in request.creative_intent
    assert "Do not render ANY text" not in request.creative_intent


def test_suppress_overlay_text_removes_the_render_instruction_and_adds_the_clean_area_instruction():
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, suppress_overlay_text=True
    )
    assert "Text overlays:" not in request.creative_intent
    assert "render NO text anywhere" in request.creative_intent


def test_suppress_overlay_text_explicitly_overrides_earlier_scene_description():
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): a real generation
    still baked a caption into the image because background_environment
    (compiled earlier, free text from an upstream AI stage) had
    independently described it as part of the scene - the old
    suppression instruction never said it overrode that. The new
    instruction must explicitly say so, and must exempt packaging text.
    """
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, suppress_overlay_text=True
    )
    assert "overrides every earlier statement in this description" in request.creative_intent
    assert "printed on the product's own packaging" in request.creative_intent


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


# --- user_feedback (Generate All feedback-driven regenerate, see MIGRATION_PLAN.md) ---


def test_no_user_feedback_instruction_when_omitted():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "a previous attempt" not in request.creative_intent


def test_user_feedback_is_quoted_verbatim_and_comes_first():
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, user_feedback="the logo is upside down"
    )

    assert '"the logo is upside down"' in request.creative_intent
    lines = request.creative_intent.splitlines()
    assert lines[0].startswith("IMPORTANT - a previous attempt")
    assert '"the logo is upside down"' in lines[0]


def test_no_retry_reason_instruction_when_omitted():
    request = compile_generation_request(_CREATIVE_SPECIFICATION, _REFERENCE_PATHS)
    assert "this is a retry" not in request.creative_intent.lower()


def test_retry_reason_is_quoted_verbatim_and_marked_as_a_retry():
    """
    Real adaptive retry (see MIGRATION_PLAN.md) - a specific, detected
    reason (not a human's own words, unlike user_feedback) must reach
    the compiled prompt honestly labeled as a retry/detected reason.
    """
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION,
        _REFERENCE_PATHS,
        retry_reason="Product identity wasn't preserved: cap shape looked rounded, not hexagonal.",
    )

    assert '"Product identity wasn\'t preserved: cap shape looked rounded, not hexagonal."' in request.creative_intent
    assert "this is a retry" in request.creative_intent.lower()


def test_user_feedback_and_retry_reason_can_both_be_present():
    """A real regenerate-with-feedback call that also auto-fails again carries both, distinctly."""
    request = compile_generation_request(
        _CREATIVE_SPECIFICATION,
        _REFERENCE_PATHS,
        user_feedback="make the background less busy",
        retry_reason="The image didn't look sufficiently realistic: warped geometry.",
    )

    assert '"make the background less busy"' in request.creative_intent
    assert '"The image didn\'t look sufficiently realistic: warped geometry."' in request.creative_intent


def test_the_text_ban_is_the_last_instruction_in_the_prompt():
    """
    Buried mid-prompt, the ban was outvoted by the composition and palette
    lines describing a "large red numeral", a "serif headline" and bullet
    points: the model rendered text-shaped content to satisfy them, and
    once the real caption was masked out of the reference it invented
    placeholder words ("Slerif Headline") instead. Stated last, it is what
    the model reconciles everything else against.
    """
    intent = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, suppress_overlay_text=True
    ).creative_intent
    assert intent.strip().endswith(")"), "the suppression block should close the prompt"
    assert intent.rindex("render NO text anywhere") > intent.rindex("Composition:")


def test_placeholder_and_decorative_lettering_are_banned_too():
    """The model satisfied a described headline with fake words."""
    intent = compile_generation_request(
        _CREATIVE_SPECIFICATION, _REFERENCE_PATHS, suppress_overlay_text=True
    ).creative_intent
    for phrase in ("placeholder", "lorem", "resembles writing", "EMPTY LAYOUT ZONE"):
        assert phrase in intent
