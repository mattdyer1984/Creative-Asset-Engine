"""
Generation prompts (Phase 1 remediation, WP-3).

The creativity-level guidance blocks are registered as FRAGMENTS
rather than separate prompts: they are alternative branches of one
instruction, so they belong to one identity. Editing either changes
this prompt's content hash even though only one fires per call -
see core.py on why unused branches still count.

Text moved here verbatim as part of WP-3; the snapshots under
tests/snapshots/prompts/ were captured before the move and pass
unchanged after it. Versions start at "1.0" because this migration
changed no wording.
"""

from app.prompts.core import register
from app.services.platform_affordances import (
    placement_instruction as platform_placement_instruction,
    strip_pointer_emoji,
)

CREATIVE_INTELLIGENCE = register(
    id="generation.creative_intelligence",
    version="1.0",
    description=(
        "Optimises the scene/background around the elements that must be preserved."
    ),
    variables=('preserved_text', 'transformable_text', 'visual_style', 'marketing_narrative', 'product_category', 'guidance'),
    fragments={
        "conservative": (
            "Optimise conservatively: choose the best version of a *similar* staging/mood to what's described below, not a dramatically different one."
        ),
        "bold": (
            "Optimise boldly: feel free to choose a meaningfully different scene within the same category, as long as the category itself stays correct and every preserved element below is still respected."
        ),
    },
    template=
"""\
You are choosing the best possible scene/background/context for a regenerated marketing creative - not a literal recreation of the original, but the single best-optimized version of the same category for this specific product, audience, and marketing strategy.

Elements that MUST remain exactly as described (do not change these, they are only given for context):
{preserved_text}

Elements that are free to be transformed/optimized (choose the single best version of each, not just any valid instance):
{transformable_text}

Creative style: {visual_style}
Marketing strategy: {marketing_narrative}
Product category: {product_category}

{guidance}

Produce one optimized_scene_description describing the ideal scene/background/environment/props to generate around the preserved elements, plus a short reasoning for your choices.""",
)


# --- Image-generation prompt compilation -----------------------------
#
# This text existed TWICE, byte-for-byte identical, in
# openai_adapter._compile_openai_prompt and
# nano_banana_adapter._compile_prompt. Two copies of the instruction
# that decides what every generated image looks like is exactly the
# drift risk the registry exists to remove: editing one and not the
# other would silently make the two providers disagree, and the
# difference would only ever show up as "the fallback produces worse
# images". One definition now; both adapters call the helper below.
IMAGE_COMPILATION = register(
    id="generation.image_compilation",
    version="1.0",
    description=(
        "Wraps the compiled creative intent with the product-preservation or "
        "story-mode instruction, plus any avoid list."
    ),
    variables=("creative_intent",),
    fragments={
        "avoid": "Avoid: {avoid_list}",
        "product_mode": (
            "Preserve the exact product shown in the reference images - its shape, "
            "proportions, colors, materials, packaging, and any visible branding or "
            "text. Only the scene, composition, lighting, and background described "
            "above should differ from the references."
        ),
        "story_mode": (
            "The reference image is the original photo for this slide - recreate "
            "its scene, composition, and mood as a NEW, original image, varying "
            "details enough that it is not an identical copy, while staying "
            "faithful to what the reference image actually shows. Do not add, "
            "invent, or feature any product - this is a narrative/story slide "
            "with none."
        ),
    },
    template="{creative_intent}",
)


def compile_image_prompt(
    creative_intent: str, *, story_mode: bool, things_to_avoid: list[str] | None = None
) -> str:
    """
    The single assembly path both image providers use.

    Kept as a function rather than a plain template because which branch
    fires is a runtime decision. Both branches still belong to
    IMAGE_COMPILATION's identity, so editing the one that did not fire
    still moves the content hash.
    """
    parts = [
        IMAGE_COMPILATION.render(creative_intent=creative_intent),
        IMAGE_COMPILATION.fragments["story_mode" if story_mode else "product_mode"],
    ]
    if things_to_avoid:
        parts.append(
            IMAGE_COMPILATION.fragments["avoid"].format(
                avoid_list="; ".join(things_to_avoid)
            )
        )
    return "\n\n".join(parts)


# --- Creative specification -------------------------------------------
#
# Two inline f-strings in openai_adapter.generate_creative_specification,
# selected by whether a Product Lock Profile exists. They shared an
# identical trailing paragraph and most of their opening clause - a
# near-duplicate the survey flagged. The shared half is now one fragment,
# so it cannot be improved in the product branch and left stale in the
# story branch.
CREATIVE_SPECIFICATION = register(
    id="generation.creative_specification",
    # 2.0: the specification is now given the source's actual overlay text
    #      and told to reproduce those blocks and only those. Previously it
    #      was asked for "suggested text overlays" with no inventory, and
    #      invented a headline/subhead/CTA set for a creative whose source
    #      carries a single caption.
    version="2.0",
    description=(
        "Composes the provider-neutral creative specification, from a Product "
        "Lock Profile plus fingerprint, or from the fingerprint alone for a "
        "story slide with no product."
    ),
    fragments={
        "focus": (
            "Focus on composition, style direction, color palette, "
            "lighting, camera and perspective, background environment, "
            "mood, text overlays, things to avoid, and aspect "
            "ratio."
        ),
        # The word "suggested" used to appear above, and the overlay role is
        # described in the schema as "headline, subhead, or cta" - between
        # them the model read the field as an invitation to write a full
        # three-part ad. case02's source carries ONE overlay block; the
        # specification produced a headline, a subhead and a "Tap the link
        # before it's gone" CTA that exists nowhere in the original. OCR had
        # the truth the whole time and this stage never looked at it.
        # Scoped to WORDS on purpose. An earlier wording said "reproduce
        # these blocks and only these", and the model read it as covering
        # every overlaid element - so it silently dropped the original's
        # pointing-emoji row, which OCR does not record as text. The list
        # constrains copy; it says nothing about non-text affordances.
        "overlay_inventory": (
            "The original creative's overlay WORDS, exactly as they appear, "
            "are listed below. Reproduce these lines of copy and no others. "
            "Do not add a headline, subhead or call-to-action the original "
            "does not have, and do not split one line into several - if the "
            "original has one line of overlay text, the specification has "
            "one. You may reword a line to suit the new image; you may not "
            "invent one.\n{blocks}\n"
            "This list covers WORDS ONLY. Non-text overlay elements - "
            "pointing emoji, arrows, stickers - are not in it and are not "
            "affected by it. If the original has them, keep them."
        ),
        "no_overlays": (
            "The original creative has NO overlay WORDS. Return an empty "
            "text_overlays array. Do not invent a headline or a "
            "call-to-action for it. This says nothing about non-text "
            "elements such as pointing emoji or arrows - if the original "
            "has them, keep them."
        ),
        "product_mode": (
            "Given the following Product Lock Profile and Creative "
            "Fingerprint for a marketing creative, compose a "
            "provider-neutral creative specification for generating a "
            "NEW, visually original marketing image that features the "
            "exact same product (per the Product Lock Profile) but is "
            "NOT a copy of the original creative - it should feel "
            "visually distinct while preserving the underlying "
            "marketing strategy captured in the Creative Fingerprint."
        ),
        "story_mode": (
            "Given the following Creative Fingerprint for a marketing "
            "creative, compose a provider-neutral creative "
            "specification for generating a NEW, visually original "
            "recreation of this creative's scene and narrative - it "
            "should feel visually distinct while preserving the "
            "underlying marketing strategy captured in the Creative "
            "Fingerprint. This slide does NOT feature a product - it "
            "is a narrative/story slide (e.g. a hook, a reaction shot, "
            "a text-only caption card). Do not invent, describe, or "
            "reference any product; focus purely on recreating the "
            "scene, composition, and mood."
        ),
    },
    template="",  # assembled entirely from fragments - see below
)


def compile_creative_specification_prompt(
    *,
    lock_profile_json: str | None,
    fingerprint_json: str,
    overlay_blocks: list[str] | None = None,
) -> str:
    """
    Assembles the product or story variant.

    `lock_profile_json=None` selects the story path - the same condition
    the adapter used (`if lock_profile is not None`), kept here so the
    branch lives with the text it selects between.

    `overlay_blocks` is the source creative's actual overlay text, from OCR.
    `None` means the caller did not look, and the prompt stays as it was -
    an unmigrated caller must not silently get an empty inventory, which
    would read as "the original has no text" and suppress every overlay.
    An empty LIST is different, and does mean exactly that.
    """
    fragments = CREATIVE_SPECIFICATION.fragments
    parts = [fragments["product_mode" if lock_profile_json is not None else "story_mode"]]
    if lock_profile_json is not None:
        parts.append(f"Product Lock Profile (JSON):\n{lock_profile_json}")
    parts.append(f"Creative Fingerprint (JSON):\n{fingerprint_json}")
    parts.append(fragments["focus"])

    if overlay_blocks is not None:
        if overlay_blocks:
            listed = "\n".join(f'  - "{text}"' for text in overlay_blocks)
            parts.append(fragments["overlay_inventory"].format(blocks=listed))
        else:
            parts.append(fragments["no_overlays"])
    return "\n\n".join(parts)


# --- Text rewrite -----------------------------------------------------
TEXT_REWRITE = register(
    id="generation.text_rewrite",
    version="1.0",
    description=(
        "Rewrites every eligible overlay text block in one call, preserving each "
        "block's role, tone and approximate length."
    ),
    variables=("block_list",),
    template=(
        "Rewrite each of the following marketing text elements, preserving "
        "its persuasive intent, tone, and approximate reading length - do "
        "not change what role it plays (a headline stays a headline, a CTA "
        "stays a CTA). Return exactly one rewritten string per input, in "
        "the same order.\n\n{block_list}"
    ),
)


# --- The generation compiler ------------------------------------------
#
# The most consequential prompt in the application: this is the text that
# actually tells the image model what to make. It had no identity at all
# because it is not a template - it is assembled from up to twelve
# conditional fragments, three of which embed unbounded free text, and
# one of which (background_environment) may itself be the output of an
# earlier AI stage.
#
# That is exactly why it needs a hash rather than why it cannot have one.
# The hash covers every FRAGMENT, not the rendered result: the rendered
# text changes on every slide, but the wording of the instructions
# changes only when someone edits it. Fragments that a given call never
# reaches are still hashed - editing the bundle-composition wording must
# be visible even on a run with no bundle.
#
# The field LABELS are prompt text too ("Composition:", "Background:"),
# not configuration, so they live here with everything else the model
# reads.
_SPEC_FIELD_LABELS = [
    ("composition", "Composition"),
    ("style_direction", "Style"),
    ("lighting", "Lighting"),
    ("camera_and_perspective", "Camera & perspective"),
    ("background_environment", "Background"),
    ("mood", "Mood"),
]


def _bundle_composition_fragment(bundle_members: list[dict]) -> str:
    """
    One line per member, with the positional reference-image ranges the
    caller concatenated them in. Structurally identical prompts differ
    here only by arithmetic, which is why the wording - not the computed
    ranges - is what carries identity.
    """
    fragments = GENERATION_COMPILER.fragments
    lines = [fragments["bundle_header"]]
    start = 1
    for member in bundle_members:
        count = member["image_count"]
        end = start + count - 1
        image_ref = (
            f"reference image {start}" if start == end else f"reference images {start}-{end}"
        )
        line = f"- {member['role_in_scene']}: shown in {image_ref}"
        member_branding_text = member.get("branding_text")
        if member_branding_text:
            quoted = "; ".join(f'"{text}"' for text in member_branding_text)
            line += fragments["bundle_member_branding"].format(quoted=quoted)
        lines.append(line)
        start = end + 1
    return "\n".join(lines)


def compile_creative_intent(
    creative_specification: dict,
    *,
    bundle_members: list[dict] | None = None,
    suppress_overlay_text: bool = False,
    branding_text: list[str] | None = None,
    user_feedback: str | None = None,
    retry_reason: str | None = None,
    source_style=None,
    typography_owned_text: list[str] | None = None,
) -> str:
    """
    Assembles the creative intent exactly as prompt_compiler always has.

    Fragment ORDER is deliberate and load-bearing: the user's own words
    come first so the model weights them highest, and the absolute
    text-suppression override comes near the end so it can override
    anything an earlier fragment said about on-screen text.
    """
    fragments = GENERATION_COMPILER.fragments
    parts: list[str] = []

    if user_feedback:
        parts.append(fragments["user_feedback"].format(user_feedback=user_feedback))
    if retry_reason:
        parts.append(fragments["retry_reason"].format(retry_reason=retry_reason))
    if bundle_members:
        parts.append(_bundle_composition_fragment(bundle_members))

    for field_name, label in _SPEC_FIELD_LABELS:
        value = creative_specification.get(field_name)
        if value:
            parts.append(f"{label}: {value}")

    color_palette = creative_specification.get("color_palette") or []
    if color_palette:
        parts.append(fragments["color_palette"] + ", ".join(color_palette))

    if branding_text:
        quoted_text = "; ".join(f'"{text}"' for text in branding_text)
        parts.append(fragments["branding_text"].format(quoted_text=quoted_text))

    if not suppress_overlay_text:
        text_overlays = creative_specification.get("text_overlays") or []
        if text_overlays:
            # A pointing emoji inside overlay copy gets drawn wherever that
            # overlay lands - on top of wherever the scene description and
            # the platform rule already place it. case02's spec asked for
            # `subhead: "right now only 👇👇👇"` AND for the same three
            # emoji in the lower left; the model drew both sets. Placement
            # is the platform's job, so the copy keeps only the words.
            overlay_text = "; ".join(
                f"{o['role']}: {strip_pointer_emoji(o['content'])}"
                for o in text_overlays
                if strip_pointer_emoji(o["content"])
            )
            if overlay_text:
                parts.append(fragments["text_overlays"] + overlay_text)

    # Style-aware, NOT unconditional. This line used to demand a real
    # photograph on every prompt regardless of the source, directly
    # contradicting an analysis that had correctly reported "digital
    # illustration, hand-drawn feel" three lines earlier. The model was
    # being asked to obey two opposite instructions, and the validator
    # then failed it for picking the analysed one.
    parts.append(fragments["transformation_policy"])
    parts.append(_rendering_instruction(source_style))

    # Where the platform's own buy button is. Not derivable from the source
    # creative - the contract records that case02's pointing emoji sit at
    # x=0.20 but not that they sit there because TikTok's buy box is bottom
    # left, so both recreations of it drifted (one centred the arrows, one
    # put the CTA bottom right). A faithful-looking image that points at
    # empty chrome does not work.
    parts.append(platform_placement_instruction())

    # Deliberately LAST. Buried mid-prompt this was outvoted by the
    # composition and palette lines above it, which describe a "large red
    # numeral", a "serif headline" and "bullet points" - the model dutifully
    # rendered text-shaped content to satisfy them, inventing placeholder
    # words like "Slerif Headline" once the real caption was masked out of
    # the reference. Stated last, it is the instruction the model reconciles
    # everything else against.
    if suppress_overlay_text:
        parts.append(fragments["suppress_overlay_text"])

    # Last, and specific: naming the exact copy someone else will place is a
    # far stronger instruction than a general ban on text.
    if typography_owned_text:
        owned = "\n".join(f'  - "{text}"' for text in typography_owned_text if text.strip())
        if owned:
            parts.append(fragments["typography_owned_text"].format(owned_text=owned))

    return "\n".join(parts)


def _rendering_instruction(source_style) -> str:
    """
    Selects the rendering-mode wording from the classified source style.

    Falls back to the source-faithful fragment when the style is unknown
    or the classifier is not confident: describing the medium as the
    analysis found it is always safe, whereas asserting a mode the
    evidence does not support is exactly the bug this replaces.
    """
    fragments = GENERATION_COMPILER.fragments
    if source_style is None:
        return fragments["render_source_faithful"]

    from app.services.source_style import RenderingFamily

    if not getattr(source_style, "is_confident", False):
        return fragments["render_source_faithful"]

    return {
        RenderingFamily.PHOTOGRAPHIC: fragments["render_photographic"],
        RenderingFamily.ILLUSTRATED: fragments["render_illustrated"],
        RenderingFamily.RENDER: fragments["render_3d"],
        RenderingFamily.MIXED: fragments["render_mixed"],
    }.get(source_style.family, fragments["render_source_faithful"])


GENERATION_COMPILER = register(
    id="generation.compiler",
    # 2.0: the rendering instruction became style-aware.
    # 3.0: text suppression strengthened and moved last, after it was
    #      shown to be outvoted by the layout prose above it.
    # 4.0: explicit transformation policy - preserve pose and composition,
    #      make the person and the environment new. Previously emergent.
    # 5.0: names the exact copy deterministic typography will place, so the
    #      model is told what NOT to render rather than only that text is
    #      banned in general (ADR 0001 WP-1.5A).
    # 6.0: states where the platform's buy button is, so a bottom CTA points
    #      at it. The first instruction here that comes from the destination
    #      platform rather than the source creative.
    # 6.1: pointer emoji are stripped from overlay copy - placement is the
    #      platform's job, and carrying one inside an overlay drew it twice.
    #      Bumped deliberately: no snapshot fixture contains an emoji, so the
    #      content hash did NOT move and neither guard would have caught this.
    version="6.1",
    description=(
        "Compiles the creative intent sent to the image model - the single most "
        "consequential prompt in the application."
    ),
    renderer=compile_creative_intent,
    fragments={
        "user_feedback": (
            "IMPORTANT - a previous attempt at this exact image had a "
            'specific problem the user flagged: "{user_feedback}". '
            "Directly address and fix this in the new image, while still "
            "following every other instruction in this description."
        ),
        "retry_reason": (
            "IMPORTANT - this is a retry: the previous attempt's best "
            "candidate failed automated quality validation for this "
            'specific, detected reason: "{retry_reason}". Directly '
            "address and fix this in the new image, while still "
            "following every other instruction in this description."
        ),
        "bundle_header": (
            "This is a BUNDLE composition: compose the following distinct products "
            "together in the same scene, matching each one's own reference photos "
            "exactly. Every product listed below must be clearly visible and "
            "recognizable in the final image - do not omit or merge any of them."
        ),
        "bundle_member_branding": (
            ". Its own packaging/label shows this exact text - reproduce it verbatim: {quoted}."
        ),
        "color_palette": "Color palette: ",
        "branding_text": (
            "The product's own packaging/label shows this exact text - reproduce "
            "it verbatim, spelled and worded exactly as given, in the same "
            "position(s) shown in the reference images: {quoted_text}."
        ),
        "suppress_overlay_text": (
            "FINAL AND ABSOLUTE INSTRUCTION - TEXT: render NO text anywhere in "
            "this image. No headline, subheadline, CTA, price, caption, "
            "callout, watermark, number, bullet point, label, or logo "
            "lettering. This includes placeholder, decorative, dummy, lorem "
            "ipsum, or nonsense letterforms - do not draw anything that even "
            "resembles writing. Wherever the description above mentions a "
            "headline, a numeral, bullet points, typography, or text colours, "
            "treat that as describing an EMPTY LAYOUT ZONE and render it as "
            "clean, uninterrupted background with nothing in it. This "
            "instruction overrides every earlier statement in this description "
            "without exception. All real copy is composited by the app "
            "afterwards, not by you. (The sole exception is text physically "
            "printed on the product's own packaging or label, which must be "
            "reproduced exactly as instructed elsewhere.)"
        ),
        "text_overlays": "Text overlays: ",
        # ADR §4 criterion 3, enforced BEFORE generation rather than only
        # checked after. A block the deterministic renderer owns must not
        # also be drawn by the model - checking afterwards tells you it went
        # wrong; naming the copy up front is what stops it.
        "typography_owned_text": (
            "TEXT OWNERSHIP: the following copy will be typeset by the "
            "application after generation and must NOT appear anywhere in "
            "your image - not as written words, not as placeholder or "
            "decorative lettering, and not paraphrased. Leave those areas as "
            "clean, uninterrupted background:\n{owned_text}"
        ),
        # What must stay the same and what must be made new. Before this
        # existed the answer was whatever the creative-specification model
        # happened to write that call: across seven slides of one run the
        # instructions ranged from "avoid copying the exact original
        # character... pose" (change the person AND the pose) to "the
        # person should visibly feel discomfort" (preserve the expression)
        # to nothing at all. Originality was emergent, not designed, and
        # two slides were told to discard the pose - the one thing that
        # should be kept.
        "transformation_policy": (
            "TRANSFORMATION POLICY - what to keep and what to make new:\n"
            "- PRESERVE EXACTLY: the product's identity, geometry, branding, "
            "colours and proportions, as shown in the reference images.\n"
            "- PRESERVE CLOSELY: camera angle, framing, composition, layout, "
            "negative space, and the visual style of the source.\n"
            "- PRESERVE BEHAVIOURALLY: any person's pose, body language, gaze "
            "direction, and how they interact with the product or the scene.\n"
            "- MAKE NEW: any person's facial identity and features, hairstyle, "
            "clothing and accessories. Generate a DIFFERENT individual of a "
            "similar age range and body type - do not reproduce the likeness "
            "of the person shown in the reference image.\n"
            "- MAKE NEW: the background environment, furniture, props and "
            "decorative objects - keep each one's functional role in the "
            "scene, but design original ones rather than copying.\n"
            "The result should read as the same creative concept, not as the "
            "same person or the same room."
        ),
        # One fragment per rendering family. Every branch is registered,
        # so editing the one that did not fire still moves the content
        # hash (see core.py).
        "render_photographic": (
            "This must look like a real photograph, not an illustration, painting, "
            "3D render, or cartoon - avoid stylized, plastic-looking, or "
            "artificial textures. Use natural photographic detail, plausible "
            "lighting, realistic anatomy and materials, and believable depth and "
            "perspective."
        ),
        "render_illustrated": (
            "This must remain an ILLUSTRATION in the same style as the source - do "
            "not convert it into a photograph. Preserve the source's level of "
            "stylisation, line quality, shading style, colour treatment, "
            "anatomical simplification, texture, and its editorial/infographic "
            "character. Anatomy should be coherent and well-drawn within that "
            "illustrated style, not photorealistic. Avoid malformed or accidental "
            "artefacts, muddy linework, and inconsistent shading."
        ),
        "render_3d": (
            "This must read as a 3D RENDER, in the same style as the source - "
            "neither a photograph nor a hand-drawn illustration. Keep the source's "
            "intended level of realism, with consistent materials, clean geometry, "
            "and coherent render lighting. Avoid modelling artefacts, intersecting "
            "geometry, and inconsistent surface shading."
        ),
        "render_mixed": (
            "This is a MIXED-MEDIA composition: keep each element in the medium the "
            "source used for it - photographic elements photographic, illustrated "
            "elements illustrated, rendered elements rendered. Do not flatten "
            "everything into one uniform medium, and do not convert the illustrated "
            "parts into photography or vice versa."
        ),
        "render_source_faithful": (
            "Match the visual medium and level of stylisation of the source "
            "creative exactly as described above - do not shift it toward a "
            "different medium."
        ),
        # The six spec field labels are prompt text as much as any
        # sentence is - the model reads "Composition:" verbatim - so they
        # belong to this prompt's identity. Held as one fragment so
        # renaming a label moves the hash.
        "spec_field_labels": "\n".join(f"{key}={label}" for key, label in _SPEC_FIELD_LABELS),
    },
    template="",  # assembled entirely from fragments, in compile_creative_intent
)


def generated_image_identity() -> dict:
    """
    The prompt identity recorded on every GeneratedImage.

    A generated image's text comes from TWO definitions: the compiler
    builds the creative intent, and the image adapter wraps it in the
    product-preservation or story-mode instruction. Both decide what the
    model sees, so both are named - editing either moves the hash.
    """
    from app.prompts.core import composite_identity

    return composite_identity(GENERATION_COMPILER, IMAGE_COMPILATION)


# --- Retry reasons ----------------------------------------------------
#
# These five strings are prompt text, not log messages. Whatever
# _summarize_rejection_reason returns is interpolated straight into the
# generation compiler's `retry_reason` fragment and read by the image
# model as an instruction about what to fix - so rewording one changes
# what the next attempt generates. They were bare literals inside a
# branching function, with no identity.
#
# Registered as one prompt because they are alternative openings of the
# same instruction, exactly one of which fires per retry: editing the
# rarely-reached photorealism branch must still move the hash.
RETRY_REASON = register(
    id="generation.retry_reason",
    # 2.0: openings became style-aware.
    version="2.0",
    description=(
        "Opens the specific, detected reason a previous attempt was rejected, "
        "which the compiler then injects into the next attempt's prompt."
    ),
    fragments={
        "identity": "Product identity wasn't preserved: ",
        "fields": "Product details didn't match: ",
        "photorealism": "The image didn't look sufficiently realistic: ",
        # Style-aware openings. The generic one above told an ILLUSTRATED
        # candidate it "didn't look sufficiently realistic", which pushed
        # each retry further from a source that was never meant to be a
        # photograph. Retry feedback must describe a real style failure,
        # never demand a change of medium.
        "style_illustrated": "The illustration quality wasn't good enough: ",
        "style_render": "The render quality wasn't good enough: ",
        "style_mixed": "The composition quality wasn't good enough: ",
        "none_passed": "No candidate in the previous attempt passed quality validation.",
        "nothing_generated": "No candidate was generated to assess.",
    },
    template="",  # one fragment is selected per retry; see the module note
)
