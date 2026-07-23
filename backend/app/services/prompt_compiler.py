"""
Prompt Compiler (Phase 8.2 of the Generation -> Validation proof of
loop; rewritten in Phase 9.3 of Product Lock v2, see MIGRATION_PLAN.md's
"ADR: Canonical Product Reference" §6). Turns a Creative Specification +
a Generation Reference Set's selected image paths into a
provider-agnostic GenerationRequest - English-language intent, never
provider-specific syntax. Compiling that intent into the literal
request a given provider's API expects is each ImageGenerationProvider's
own job (see app.ai_providers.openai_adapter.
OpenAIImageGenerationAdapter), not this module's - that boundary is
what keeps everything upstream of a provider provider-agnostic.

Phase 9.3 rewrite: no longer takes a ProductProfile, no longer compiles
immutable_constraints at all. The product is no longer described in
text - reference_image_paths (the Reference Selection service's chosen
subset of the Canonical Reference Library) are the only source of
product identity a generation call carries; the compiler's job narrows
to scene, composition, and marketing intent - everything AROUND the
product, never the product itself. "subject" - the one Creative
Specification field that describes the product rather than the scene -
is dropped from _CREATIVE_SPEC_INTENT_FIELDS for the same reason,
mirroring CANONICAL_FIELD_VOCABULARY's own immutable/contextual split
(Phase 5.5): what's kept here is exactly the "contextual" half.

reference_image_paths is a hard prerequisite, not optional - this
function raises ValueError if given an empty list, rather than silently
compiling a product-blind, text-only request. This is a deliberate,
reviewed design decision (ADR §6/§10), not an oversight: a generation
call with no reference images has nothing to condition product fidelity
on, and Product Lock v2's whole point is that this should never happen
silently.

bundle_members (Phase 10.7, AI Creative Engine vNext §12's "Bundle
Composition" addendum) is the one addition since the Phase 9.3 rewrite
above - still additive, still optional, still no new I/O. When given,
it's plain, precomputed data (role_in_scene + how many of
reference_image_paths belong to that member, in the same order the
caller concatenated them - see app.services.generation_engine.
run_bundle_generation_attempt), used only to build one explicit
instruction telling the provider which reference images belong to
which distinct product and what part it plays in the scene. This
phrasing (list each product's role, point at its specific reference
images by position) is the exact structure a real, live-verified spike
confirmed works: a real generation call given two genuinely different
products' reference images, with this kind of positional callout,
composed both together correctly in one photorealistic scene - see
that phase's report in MIGRATION_PLAN.md.

Still a pure function - no I/O, no DB queries, no provider calls,
trivially unit-testable with plain dicts and a plain list of path
strings. Reference Selection (a separate service, app.services.
reference_selection) is what actually queries the Library and asks a
provider's capabilities for max_reference_images - by the time its
output reaches this function, it's already just data.

"Platform Rules" (aspect ratio defaults per target platform) is
deliberately minimal here - a plain fallback dict, not a persisted
entity. Proving the loop once, for one slide, one provider, doesn't
need a real Platform Rules subsystem; see the architecture direction's
explicit scope decision on this.
"""

from app.ai_providers.base import GenerationRequest
from app.product_sources.base import ColorValue, DimensionValue, ListValue, NumberValue, TextValue

_PLATFORM_DEFAULT_ASPECT_RATIOS = {
    "generic": "1:1",
}

# (CreativeSpecification field, human-readable label) - order here is the
# order they appear in the compiled creative_intent text. "subject" is
# deliberately absent (Phase 9.3) - it's the one field that describes
# the product itself, and the reference images are the only source of
# product identity now, not text.
_CREATIVE_SPEC_INTENT_FIELDS = [
    ("composition", "Composition"),
    ("style_direction", "Style"),
    ("lighting", "Lighting"),
    ("camera_and_perspective", "Camera & perspective"),
    ("background_environment", "Background"),
    ("mood", "Mood"),
]


def format_attribute_value(value) -> str:
    """
    Renders one canonical ProductAttributeValue (see
    app.product_sources.base) as a short human-readable phrase. Public
    (not module-private) since app.slideshow_stages.image_validation_stage
    (Phase 8.4) reuses this exact formatting for consistency between what
    Generation was told to preserve and what Validation displays back -
    unchanged by the Phase 9.3 rewrite, since Validation still compares
    against the canonical Product Profile's immutable fields even though
    Generation itself no longer describes them in text.
    """
    if isinstance(value, TextValue):
        return value.text
    if isinstance(value, ColorValue):
        return value.label + (f" ({value.hex})" if value.hex else "")
    if isinstance(value, DimensionValue):
        parts = [p for p in (value.length, value.width, value.height) if p is not None]
        return (" x ".join(str(p) for p in parts) + f" {value.unit}") if parts else value.unit
    if isinstance(value, NumberValue):
        return f"{value.value}" + (f" {value.unit}" if value.unit else "")
    if isinstance(value, ListValue):
        return ", ".join(value.items)
    return str(value)


def _bundle_composition_instruction(bundle_members: list[dict]) -> str:
    lines = [
        "This is a BUNDLE composition: compose the following distinct products "
        "together in the same scene, matching each one's own reference photos "
        "exactly. Every product listed below must be clearly visible and "
        "recognizable in the final image - do not omit or merge any of them."
    ]
    start = 1
    for member in bundle_members:
        count = member["image_count"]
        end = start + count - 1
        image_ref = f"reference image {start}" if start == end else f"reference images {start}-{end}"
        lines.append(f"- {member['role_in_scene']}: shown in {image_ref}")
        start = end + 1
    return "\n".join(lines)


def compile_generation_request(
    creative_specification: dict,
    reference_image_paths: list[str],
    platform: str = "generic",
    bundle_members: list[dict] | None = None,
) -> GenerationRequest:
    """
    creative_specification is a CreativeSpecification.structured_json
    dict (composition/style_direction/... - see
    CREATIVE_SPECIFICATION_AI_SCHEMA in
    app.slideshow_stages.creative_specification_stage).

    reference_image_paths is Reference Selection's output (§6/§7 of the
    Product Lock v2 ADR) - the Generation Reference Set's chosen Library
    image file paths, already resolved to real files on disk by the
    caller. This function does not read them - reading happens in the
    provider adapter, which needs the actual bytes to call a real API;
    this function only carries the paths through as plain data.

    bundle_members (Phase 10.7, §12's Bundle Composition addendum): a
    list of `{"role_in_scene": str, "image_count": int}` in the same
    order the caller concatenated each member's own reference images
    into reference_image_paths - see this function's own module
    docstring for why this exists and what confirmed it works.
    """
    if not reference_image_paths:
        raise ValueError(
            "compile_generation_request requires at least one reference image path - "
            "Reference Selection must run first and produce a non-empty Generation "
            "Reference Set. Product Lock v2 makes this a hard prerequisite, not an "
            "optional enhancement with a text-only fallback."
        )

    intent_parts = []
    if bundle_members:
        intent_parts.append(_bundle_composition_instruction(bundle_members))

    for field_name, label in _CREATIVE_SPEC_INTENT_FIELDS:
        value = creative_specification.get(field_name)
        if value:
            intent_parts.append(f"{label}: {value}")

    color_palette = creative_specification.get("color_palette") or []
    if color_palette:
        intent_parts.append("Color palette: " + ", ".join(color_palette))

    text_overlays = creative_specification.get("text_overlays") or []
    if text_overlays:
        overlay_text = "; ".join(f"{o['role']}: {o['content']}" for o in text_overlays)
        intent_parts.append(f"Text overlays: {overlay_text}")

    things_to_avoid = list(creative_specification.get("things_to_avoid") or [])

    aspect_ratio = creative_specification.get("aspect_ratio") or _PLATFORM_DEFAULT_ASPECT_RATIOS.get(
        platform, _PLATFORM_DEFAULT_ASPECT_RATIOS["generic"]
    )

    return GenerationRequest(
        creative_intent="\n".join(intent_parts),
        reference_image_paths=reference_image_paths,
        things_to_avoid=things_to_avoid,
        aspect_ratio=aspect_ratio,
    )
