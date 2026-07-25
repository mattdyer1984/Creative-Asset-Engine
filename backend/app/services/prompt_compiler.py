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
from app.prompts import generation as _generation_prompts
from app.prompts.generation import GENERATION_COMPILER

# (CreativeSpecification field, human-readable label) - order here is the
# order they appear in the compiled creative_intent text. "subject" is
# deliberately absent (Phase 9.3) - it's the one field that describes
# the product itself, and the reference images are the only source of
# product identity now, not text.
# The field labels moved to the registered prompt definition (WP-3) -
# "Composition:" is text the model reads, so it is prompt content.
_CREATIVE_SPEC_INTENT_FIELDS = _generation_prompts._SPEC_FIELD_LABELS


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


def compile_generation_request(
    creative_specification: dict,
    reference_image_paths: list[str],
    bundle_members: list[dict] | None = None,
    suppress_overlay_text: bool = False,
    branding_text: list[str] | None = None,
    user_feedback: str | None = None,
    story_mode: bool = False,
    retry_reason: str | None = None,
    source_style=None,
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

    # WP-3: the prompt text and its assembly order now live on the
    # registered prompt definition (app/prompts/generation.py), so the
    # most consequential prompt in the application has an id, a semantic
    # version and a content hash like every other one. This function
    # keeps its signature, its validation, and its job of turning the
    # compiled text into a provider-neutral GenerationRequest.
    creative_intent = GENERATION_COMPILER.assemble(
        creative_specification,
        bundle_members=bundle_members,
        suppress_overlay_text=suppress_overlay_text,
        branding_text=branding_text,
        user_feedback=user_feedback,
        retry_reason=retry_reason,
        source_style=source_style,
    )

    things_to_avoid = list(creative_specification.get("things_to_avoid") or [])

    return GenerationRequest(
        creative_intent=creative_intent,
        reference_image_paths=reference_image_paths,
        things_to_avoid=things_to_avoid,
        aspect_ratio="3:4",
        story_mode=story_mode,
    )
