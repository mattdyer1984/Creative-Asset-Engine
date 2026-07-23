"""
Prompt Compiler (Phase 8.2 of the Generation -> Validation proof of
loop, see MIGRATION_PLAN.md's architecture direction). Turns a Creative
Specification + the canonical Product Profile into a provider-agnostic
GenerationRequest - English-language intent, never provider-specific
syntax. Compiling that intent into the literal request a given
provider's API expects is each ImageGenerationProvider's own job (see
app.ai_providers.openai_adapter.OpenAIImageGenerationAdapter), not this
module's - that boundary is what keeps everything upstream of a
provider provider-agnostic, per the user's explicit instruction.

"Platform Rules" (aspect ratio defaults per target platform) is
deliberately minimal here - a plain fallback dict, not a persisted
entity. Proving the loop once, for one slide, one provider, doesn't
need a real Platform Rules subsystem; see the architecture direction's
explicit scope decision on this.
"""

from app.ai_providers.base import GenerationRequest
from app.product_sources.base import ColorValue, DimensionValue, ListValue, NumberValue, TextValue
from app.services.product_profile import ProductProfile

_PLATFORM_DEFAULT_ASPECT_RATIOS = {
    "generic": "1:1",
}

# (CreativeSpecification field, human-readable label) - order here is the
# order they appear in the compiled creative_intent text.
_CREATIVE_SPEC_INTENT_FIELDS = [
    ("subject", "Subject"),
    ("composition", "Composition"),
    ("style_direction", "Style"),
    ("lighting", "Lighting"),
    ("camera_and_perspective", "Camera & perspective"),
    ("background_environment", "Background"),
    ("mood", "Mood"),
]


def _format_attribute_value(value) -> str:
    """Renders one canonical ProductAttributeValue (see app.product_sources.base) as a short human-readable phrase."""
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


def compile_generation_request(
    creative_specification: dict,
    product_profile: ProductProfile,
    platform: str = "generic",
) -> GenerationRequest:
    """
    creative_specification is a CreativeSpecification.structured_json
    dict (subject/composition/style_direction/... - see
    CREATIVE_SPECIFICATION_AI_SCHEMA in
    app.slideshow_stages.creative_specification_stage).

    immutable_constraints is compiled from the canonical ProductProfile,
    not re-derived from the Creative Specification - what must be
    preserved comes from the Product Profile's own immutable/contextual
    classification (Phase 5.5), never guessed at here.
    """
    intent_parts = []
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

    immutable_constraints = [
        f"{field_name}: {_format_attribute_value(field.value)}"
        for field_name, field in product_profile.fields.items()
        if field.classification == "immutable"
    ]

    things_to_avoid = list(creative_specification.get("things_to_avoid") or [])

    aspect_ratio = creative_specification.get("aspect_ratio") or _PLATFORM_DEFAULT_ASPECT_RATIOS.get(
        platform, _PLATFORM_DEFAULT_ASPECT_RATIOS["generic"]
    )

    return GenerationRequest(
        creative_intent="\n".join(intent_parts),
        immutable_constraints=immutable_constraints,
        things_to_avoid=things_to_avoid,
        aspect_ratio=aspect_ratio,
    )
