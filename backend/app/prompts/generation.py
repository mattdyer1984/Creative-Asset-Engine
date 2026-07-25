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
