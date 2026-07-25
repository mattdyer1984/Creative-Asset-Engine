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

Aspect ratio is a hardcoded, unconditional "3:4" (real-world-diagnosed
fix, see MIGRATION_PLAN.md) - not a per-platform "Platform Rules"
lookup (an earlier, more speculative design here that never grew past
one entry) and not read from `creative_specification`'s own AI-inferred
field (typically "9:16 vertical social media frame", matching whatever
aspect the source slide happened to be). Once actually posted to
TikTok, the app's own UI (like/comment/share icons, caption bar,
username) covers a real, fixed strip of any 9:16 frame - 3:4 leaves
enough of that away from the final crop that it doesn't overlap what
this app renders. A flat product policy, not a per-creative judgment
call, so it's asserted here rather than asked of any AI stage.
"""

from app.ai_providers.base import GenerationRequest
from app.product_sources.base import ColorValue, DimensionValue, ListValue, NumberValue, TextValue

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
        line = f"- {member['role_in_scene']}: shown in {image_ref}"
        member_branding_text = member.get("branding_text")
        if member_branding_text:
            quoted = "; ".join(f'"{text}"' for text in member_branding_text)
            line += f". Its own packaging/label shows this exact text - reproduce it verbatim: {quoted}."
        lines.append(line)
        start = end + 1
    return "\n".join(lines)


def compile_generation_request(
    creative_specification: dict,
    reference_image_paths: list[str],
    bundle_members: list[dict] | None = None,
    suppress_overlay_text: bool = False,
    branding_text: list[str] | None = None,
    user_feedback: str | None = None,
    story_mode: bool = False,
    retry_reason: str | None = None,
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
    docstring for why this exists and what confirmed it works. Each
    member dict may also carry an optional `"branding_text": list[str]`
    (same real-world-diagnosed fix as the top-level branding_text
    param below, applied per-member since a bundle scene has no single
    product to attribute packaging text to).

    branding_text (real-world-diagnosed fix, see MIGRATION_PLAN.md): the
    exact text printed on the product's own packaging/label
    (app.services.product_profile.extract_branding_text, the same
    extraction Stage 2 validation's branding_text field_check compares
    against). Phase 9.3 deliberately dropped all product description
    from this prompt in favor of reference-image conditioning alone -
    correct for physical geometry, but reference images alone give the
    model no reliable way to know precisely which characters make up
    small printed label text, so branding_text validation failed on
    most real generations. This is a narrow, deliberate exception to
    the "no product text" rule (ADR §6) - not text describing the
    product, but a verbatim transcript of text the product itself
    already carries, given to help the model reproduce it correctly.

    suppress_overlay_text (Phase 10.8, §9): False by default, on
    purpose - a real, deliberate backward-compatibility decision, not
    an oversight. Before Phase 10.8, `creative_specification.
    text_overlays` was always included as a literal render instruction
    (the model was asked to bake marketing text into the pixels - the
    original, still-supported behavior for any caller that hasn't
    adopted the new Text Intelligence/Rendering Engine flow). Only a
    caller that has genuinely opted into a real `text_strategy`
    (app.services.decision_engine's `GenerationPlan.text_strategy`)
    passes True here - suppressing that literal instruction and
    replacing it with an explicit "leave this area clean, the app
    composites it separately" instruction, since asking the model to
    render text AND the app to composite text over the same area would
    produce visibly broken, doubled-up output.

    **Real-world-diagnosed strengthening** (see MIGRATION_PLAN.md): this
    suppression only ever addressed `creative_specification.
    text_overlays` - a real generation showed the model still baking a
    caption into the image anyway, because `background_environment`
    (compiled above, in `_CREATIVE_SPEC_INTENT_FIELDS`) is free text
    written by an earlier AI stage, and that stage had independently
    described the on-screen caption as part of "the scene" (e.g. "keep
    the on-screen caption... reading '...'"). That framing never
    matches the words "headline"/"CTA"/"price" the old suppression
    instruction listed, so the model saw two instructions that didn't
    look like they conflicted and rendered the caption anyway. The
    instruction below is now an explicit, absolute override of
    anything stated earlier in this same compiled prompt, not just a
    parallel instruction alongside it.

    user_feedback (Generate All, see MIGRATION_PLAN.md): a free-text
    note from a per-slide regenerate action describing what was wrong
    with a previous attempt. Deliberately distinct from
    decision_engine.py's `retry_reason` (an internal, generic
    validation-failure signal, never seen by the model) - this is the
    user's own words, given directly to the model as the first,
    highest-priority instruction so it can actually act on it.

    story_mode (Story Slide feature, see MIGRATION_PLAN.md): False by
    default, unaffected for every pre-existing caller. Just threaded
    through onto the returned GenerationRequest here - this function's
    own compiled creative_intent text doesn't change either way (it
    never described the product anyway, only the scene); each adapter's
    `_compile_*_prompt` is what reads this flag to swap its own
    "preserve the exact product" instruction for a "recreate this scene
    with subtle originality" one when there's no product to preserve.

    retry_reason (real adaptive retry, see MIGRATION_PLAN.md and
    decision_engine.py's own module docstring - this is the "later
    sub-phase" that docstring named as the reason retry_reason was
    carried through and persisted from the start): the *specific*,
    real reason the previous attempt's best candidate was rejected
    (e.g. "Product identity wasn't preserved: cap shape looked
    rounded, not hexagonal"), built by generate_with_retry.py from the
    actual QualityAssessment/ImageValidationResult data, not a generic
    placeholder. Deliberately a separate instruction from
    `user_feedback` (a human's own words) rather than merged into it -
    both can be present at once (a user's regenerate note on a retry
    that also auto-failed again), and conflating "the system detected"
    with "the user said" would be dishonest about the source.
    """
    if not reference_image_paths:
        raise ValueError(
            "compile_generation_request requires at least one reference image path - "
            "Reference Selection must run first and produce a non-empty Generation "
            "Reference Set. Product Lock v2 makes this a hard prerequisite, not an "
            "optional enhancement with a text-only fallback."
        )

    intent_parts = []
    if user_feedback:
        intent_parts.append(
            "IMPORTANT - a previous attempt at this exact image had a "
            f'specific problem the user flagged: "{user_feedback}". '
            "Directly address and fix this in the new image, while still "
            "following every other instruction in this description."
        )
    if retry_reason:
        intent_parts.append(
            "IMPORTANT - this is a retry: the previous attempt's best "
            f'candidate failed automated quality validation for this '
            f'specific, detected reason: "{retry_reason}". Directly '
            "address and fix this in the new image, while still "
            "following every other instruction in this description."
        )
    if bundle_members:
        intent_parts.append(_bundle_composition_instruction(bundle_members))

    for field_name, label in _CREATIVE_SPEC_INTENT_FIELDS:
        value = creative_specification.get(field_name)
        if value:
            intent_parts.append(f"{label}: {value}")

    color_palette = creative_specification.get("color_palette") or []
    if color_palette:
        intent_parts.append("Color palette: " + ", ".join(color_palette))

    if branding_text:
        quoted_text = "; ".join(f'"{text}"' for text in branding_text)
        intent_parts.append(
            "The product's own packaging/label shows this exact text - reproduce "
            "it verbatim, spelled and worded exactly as given, in the same "
            f"position(s) shown in the reference images: {quoted_text}."
        )

    if suppress_overlay_text:
        intent_parts.append(
            "Do not render ANY text of any kind into the image - no marketing "
            "headline, subheadline, CTA, price, caption, callout, or watermark. "
            "This overrides anything stated earlier in this description that "
            "mentions or quotes on-screen text or a caption as part of the "
            "scene - ignore that and leave every such area visually clean and "
            "uncluttered instead. All of that text is composited separately by "
            "the app afterward, not by you. (This does not apply to text "
            "physically printed on the product's own packaging or label - "
            "reproduce that exactly, as instructed elsewhere in this "
            "description.)"
        )
    else:
        text_overlays = creative_specification.get("text_overlays") or []
        if text_overlays:
            overlay_text = "; ".join(f"{o['role']}: {o['content']}" for o in text_overlays)
            intent_parts.append(f"Text overlays: {overlay_text}")

    # Phase 10.8, §9 Revision #1 - unconditional, every prompt, every
    # strategy: a real photograph, not an illustration. Photorealism is
    # already a hard-floor Quality Engine dimension (Phase 10.3); asking
    # for it explicitly up front is the same objective, stated earlier
    # in the pipeline rather than only measured after the fact.
    intent_parts.append(
        "This must look like a real photograph, not an illustration, painting, "
        "3D render, or cartoon - avoid stylized, plastic-looking, or "
        "artificial textures."
    )

    things_to_avoid = list(creative_specification.get("things_to_avoid") or [])

    return GenerationRequest(
        creative_intent="\n".join(intent_parts),
        reference_image_paths=reference_image_paths,
        things_to_avoid=things_to_avoid,
        aspect_ratio="3:4",
        story_mode=story_mode,
    )
