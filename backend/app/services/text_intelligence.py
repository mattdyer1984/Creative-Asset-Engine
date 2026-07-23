"""
Text Intelligence — Phase 10.8 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §9). Scoped, per
that section's own explicit conflict resolution, to marketing-overlay
text only (headlines/CTAs/etc. a designer would set in a design tool) -
never text physically printed on the product's own packaging, which
Product Lock v2 already treats as an immutable Product Profile field
(`branding_text`) the image model itself must preserve. Text
Intelligence and Product Lock v2 stay in separate lanes by
construction: this module never touches product identity.

**Real, additive correction to §9's own assumption, made as this
phase's first step**: §9 assumed "reuse_original extracts TextAssets
from existing OCR/layout data (already largely available via
OCRResult.structured_blocks_json)." Investigated and found false -
OCR's real, shipped response shape was `{text, role}` only, no
position, nothing to extract a layout from. `OCR_RESPONSE_SCHEMA`
(app.ai_providers.openai_adapter) gained a real `bounding_box` per
block as this phase's own prerequisite fix, the same x_min/y_min/
x_max/y_max normalized (0.0-1.0) convention Scene Intelligence's own
regions already use - not a new convention invented for this. A slide
analyzed before this phase (its current OCRResult has no bounding_box)
has nothing to reuse; `reuse_original` returns no TextAssets for those
blocks, the same tri-state discipline this codebase already holds
everywhere else a genuinely new prerequisite doesn't exist yet for
older data - not an error, just nothing to reuse.

**Typography is deliberately NOT literally extracted or font-matched**
- identifying an arbitrary real font from pixels is a genuinely hard,
unsolved problem this codebase makes no claim to solve, and this ADR
never asked for it (§9 only ever says "typography... extracted or
chosen", explicitly leaving room for "chosen"). Font weight/size here
are a deterministic function of `hierarchy` (computed in code from
`role`, never asked of an AI), rendered by
app.services.rendering_engine with Pillow's own bundled default font
(`PIL.ImageFont.load_default`) - portable everywhere Pillow runs, no
external font files to source, download, or license. A real,
live-verified feasibility spike (see this phase's report in
MIGRATION_PLAN.md) confirmed this combination - deterministic sizing +
a semi-transparent legibility scrim - reads as clean, professional
overlay text even over a busy, real generated photograph, not the
harder, unsolved problem of exact typographic reproduction.

A TextAsset is a plain dict, not its own DB table (deliberately,
mirroring SceneAnalysis.regions_json's own "no separate join table,
these have no identity of their own" precedent) - it only ever exists
nested inside one FinalOutput.text_assets_json (app.models.final_output);
nothing needs to query a TextAsset independently of its own output.
"""

from app.models.ocr_result import OCRResult

TEXT_STRATEGY_REUSE_ORIGINAL = "reuse_original"
TEXT_STRATEGY_AI_REWRITE = "ai_rewrite"
TEXT_STRATEGY_NO_TEXT = "no_text"
TEXT_STRATEGIES = {TEXT_STRATEGY_REUSE_ORIGINAL, TEXT_STRATEGY_AI_REWRITE, TEXT_STRATEGY_NO_TEXT}

# Which OCR roles are marketing-overlay text at all, and the hierarchy
# tier each maps to. logo_text is product packaging (Product Lock's
# job, never this module's); disclaimer/other are real, lower-priority
# fine print explicitly out of this phase's scope, not silently lost -
# they remain visible in OCRResult.raw_text/structured_blocks_json,
# just never promoted to a rendered overlay.
_ROLE_TO_HIERARCHY = {
    "headline": "headline",
    "subheadline": "subhead",
    "price": "subhead",
    "cta": "cta",
}

# hierarchy -> deterministic styling, computed in code (see module
# docstring for why this isn't literal font extraction).
_HIERARCHY_STYLE = {
    "headline": {"size_class": "large", "weight": "bold", "render_style": "scrim"},
    "subhead": {"size_class": "medium", "weight": "regular", "render_style": "scrim"},
    "cta": {"size_class": "medium", "weight": "bold", "render_style": "badge"},
}

# hierarchy -> semantic_role, reusing NarrativeStructure's own beat
# vocabulary (§9's own explicit instruction) rather than a parallel one.
_HIERARCHY_SEMANTIC_ROLE = {"headline": "hook", "subhead": "proof", "cta": "cta"}

_REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "rewritten": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["rewritten"],
    "additionalProperties": False,
}


def _eligible_blocks(ocr_result: OCRResult | None) -> list[dict]:
    if ocr_result is None:
        return []
    return [
        block
        for block in ocr_result.structured_blocks_json
        if block.get("role") in _ROLE_TO_HIERARCHY and block.get("bounding_box")
    ]


def _text_asset_from_block(block: dict, wording: str) -> dict:
    hierarchy = _ROLE_TO_HIERARCHY[block["role"]]
    style = _HIERARCHY_STYLE[hierarchy]
    bbox = block["bounding_box"]
    return {
        "wording": wording,
        "hierarchy": hierarchy,
        "semantic_role": _HIERARCHY_SEMANTIC_ROLE[hierarchy],
        "positioning": {
            "x": bbox["x_min"],
            "y": bbox["y_min"],
            "width": max(bbox["x_max"] - bbox["x_min"], 0.05),
        },
        "styling": {
            "size_class": style["size_class"],
            "weight": style["weight"],
            "render_style": style["render_style"],
        },
    }


def build_text_assets(
    text_strategy: str,
    ocr_result: OCRResult | None,
    *,
    text_generation_provider=None,
) -> list[dict]:
    """
    Returns the list of TextAsset dicts the Rendering Engine should
    composite. `no_text` (and any slide with nothing eligible to
    reuse) returns `[]` - a real, valid outcome the Rendering Engine
    treats as a straight pass-through, not an error.
    """
    if text_strategy not in TEXT_STRATEGIES:
        raise ValueError(f"Unknown text_strategy {text_strategy!r} - must be one of {sorted(TEXT_STRATEGIES)}")

    if text_strategy == TEXT_STRATEGY_NO_TEXT:
        return []

    blocks = _eligible_blocks(ocr_result)
    if not blocks:
        return []

    if text_strategy == TEXT_STRATEGY_REUSE_ORIGINAL:
        return [_text_asset_from_block(block, block["text"]) for block in blocks]

    # ai_rewrite: same positions/hierarchy as reuse_original (§9's own
    # "producing new wording while keeping the extracted typography/
    # positioning"), only the wording itself changes - one real call
    # rewriting every eligible block together, not one call per block.
    if text_generation_provider is None:
        raise ValueError("text_strategy='ai_rewrite' requires a text_generation_provider")

    prompt = (
        "Rewrite each of the following marketing text elements, preserving "
        "its persuasive intent, tone, and approximate reading length - do "
        "not change what role it plays (a headline stays a headline, a CTA "
        "stays a CTA). Return exactly one rewritten string per input, in "
        "the same order.\n\n"
        + "\n".join(f'{i + 1}. [{b["role"]}] "{b["text"]}"' for i, b in enumerate(blocks))
    )
    result = text_generation_provider.generate(
        prompt_spec={"prompt": prompt, "schema_name": "text_rewrite"},
        response_schema=_REWRITE_SCHEMA,
    )
    rewritten = result["rewritten"]
    if len(rewritten) != len(blocks):
        raise ValueError(
            f"ai_rewrite returned {len(rewritten)} rewritten strings for {len(blocks)} blocks - "
            "must be exactly one per block, in order."
        )

    return [_text_asset_from_block(block, wording) for block, wording in zip(blocks, rewritten)]
