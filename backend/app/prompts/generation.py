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
