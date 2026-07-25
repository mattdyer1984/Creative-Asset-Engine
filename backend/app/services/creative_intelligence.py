"""
Creative Intelligence — Phase 10.4 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §8, the decision
layer half). Consumes Scene Intelligence's `SceneAnalysis` (same
sub-phase) to decide, per region, whether to preserve or transform -
and for transformable regions, produces one **optimized** scene
description, not a literal recreation.

**Preserve vs. transform is a deterministic mapping from
`importance_tier`, computed in code, never asked of the AI** -
essential/important always preserve, context/incidental/replaceable
always transform, per the ADR's own explicit definition. The one real
AI judgment this module makes is the *content* of the transform: given
what must stay untouched, what's free to change, the creative's own
style/strategy, the product's category, and a creativity_level dial,
choose the single best-optimized version of each transformable
category for this specific creative - "contextually optimise," not
"contextually match" (Revision #5's naming). Reuses
`TextGenerationProvider.generate` unchanged (the same capability
Marketing Analysis already uses for text-only structured generation) -
no new provider capability needed.

**Feeds the Prompt Compiler as a new input, without redesigning it**
(§8's own explicit instruction): the caller (Generation Engine) merges
`optimized_scene_description` into a *copy* of the Creative
Specification's `background_environment` field before calling
`compile_generation_request` - not a new parameter on that already-pure
function, not a new call path.

Tri-state, matching this codebase's staleness/narrative-beat
discipline: a slide with no `SceneAnalysis` yet (analyzed before this
sub-phase shipped, or Scene Intelligence hasn't run) has nothing for
this module to work from - the caller skips straight to the original,
un-enriched Creative Specification, exactly as it worked before this
sub-phase existed. Never a hard failure.
"""

from app.ai_providers.registry import default_registry
from app.prompts import generation as _generation_prompts
from app.services.provider_call_log import record_provider_call
import time

from sqlalchemy.orm import Session

from app.models.scene_analysis import SceneAnalysis

CREATIVE_INTELLIGENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "optimized_scene_description": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["optimized_scene_description", "reasoning"],
    "additionalProperties": False,
}

_PRESERVE_TIERS = {"essential", "important"}

# The two guidance branches are fragments of the creative-intelligence
# prompt (WP-3), not separate prompts: they are alternative wordings of
# one instruction. Editing either moves that prompt's content hash even
# though only one fires per call - see app/prompts/core.py on why an
# unused branch still counts toward identity.
_CREATIVITY_LEVEL_GUIDANCE = dict(_generation_prompts.CREATIVE_INTELLIGENCE.fragments)


def region_decision(importance_tier: str) -> str:
    """
    The ADR's own explicit, deterministic mapping - essential/important
    preserve, context/incidental/replaceable transform. A pure function,
    not an AI judgment: "should this region be touched at all" is
    already fully determined by Scene Intelligence's own tier, the
    thing worth asking the AI is only what a transform should become.
    """
    return "preserve" if importance_tier in _PRESERVE_TIERS else "transform"


def _build_creative_intelligence_prompt(
    preserved_notes: list[str],
    transformable_notes: list[str],
    visual_style: str,
    marketing_narrative: str,
    product_category: str,
    creativity_level: str,
) -> str:
    preserved_text = "\n".join(f"- {note}" for note in preserved_notes) or "- (none)"
    transformable_text = "\n".join(f"- {note}" for note in transformable_notes) or "- (none)"
    guidance = _CREATIVITY_LEVEL_GUIDANCE.get(creativity_level, _CREATIVITY_LEVEL_GUIDANCE["conservative"])

    return _generation_prompts.CREATIVE_INTELLIGENCE.render(
        preserved_text=preserved_text,
        transformable_text=transformable_text,
        visual_style=visual_style,
        marketing_narrative=marketing_narrative,
        product_category=product_category,
        guidance=guidance,
    )


def optimize_scene_description(
    scene_analysis: SceneAnalysis,
    *,
    visual_style: str,
    marketing_narrative: str,
    product_category: str,
    creativity_level: str = "conservative",
    db: Session | None = None,
) -> dict:
    preserved_notes = [
        region["notes"] for region in scene_analysis.regions_json
        if region_decision(region["importance_tier"]) == "preserve"
    ]
    transformable_notes = [
        region["notes"] for region in scene_analysis.regions_json
        if region_decision(region["importance_tier"]) == "transform"
    ]

    text_provider = default_registry.text_generation()
    usage: dict = {}
    start = time.perf_counter()
    result = text_provider.generate(
        prompt_spec={
            "prompt": _build_creative_intelligence_prompt(
                preserved_notes, transformable_notes, visual_style,
                marketing_narrative, product_category, creativity_level,
            ),
            "schema_name": "creative_intelligence",
        },
        response_schema=CREATIVE_INTELLIGENCE_SCHEMA,
        usage_sink=usage,
    )
    # Phase 1 remediation (WP-2): this was one of four modules making a
    # real paid call with no record at all. `db` is optional so the pure
    # function stays independently testable; every production caller
    # passes it.
    if db is not None:
        record_provider_call(
            db,
            provider=text_provider.provider,
            model=text_provider.model,
            capability="text_generation",
            prompt=_generation_prompts.CREATIVE_INTELLIGENCE,
            usage=usage,
            provider_latency_ms=(time.perf_counter() - start) * 1000,
        )
    return result
