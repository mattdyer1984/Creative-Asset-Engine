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

**Second real, additive correction, real-world-diagnosed** (see
MIGRATION_PLAN.md): "marketing-overlay text" turned out not to be
fully determined by `role` alone - a real generation showed OCR
tagging text physically printed on the product's own packaging, and
separately a shelf's own price tags, with roles ("headline", "price")
this module otherwise treats as overlay-eligible, causing the
Rendering Engine to duplicate text the base image generation had
already faithfully reproduced as part of the photographed scene. OCR's
`OCR_RESPONSE_SCHEMA` gained an explicit per-block `surface` field
("physical" vs "overlay") as this correction's own prerequisite fix -
see `_eligible_blocks`' own docstring for the full reasoning and the
tri-state handling of pre-migration OCR data with no `surface` at all.

**Typography is deliberately NOT literally extracted or font-matched**
- identifying an arbitrary real font from pixels is a genuinely hard,
unsolved problem this codebase makes no claim to solve, and this ADR
never asked for it (§9 only ever says "typography... extracted or
chosen", explicitly leaving room for "chosen"). Font size here is a
deterministic function of `hierarchy` (computed in code from `role`,
never asked of an AI); everything else about how it's drawn (real bold
system typeface, black stroke outline, centered, no background box) is
a single, unconditional style app.services.rendering_engine applies to
every TextAsset - a real-world-diagnosed, user-directed simplification
(see MIGRATION_PLAN.md) from the original per-hierarchy scrim/badge
design: a real generated image's overlay boxes read as inconsistent
and visually heavy (a solid black rectangle behind every line), and
the user asked for one consistent treatment matching how the original
creator's own on-screen caption actually looked - centered, stroked,
no box - rather than a design system per marketing role.

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

# role -> hierarchy tier, for the four roles OCR classifies clearly
# enough to size distinctly. Real-world-diagnosed correction (Generate
# All follow-up, see MIGRATION_PLAN.md): this used to also gate
# *inclusion* (see the old version of `_eligible_blocks`, which
# required `role in _ROLE_TO_HIERARCHY`) - a real caption's third line
# ("what have they done😭😭😭") came back from OCR correctly marked
# `surface: "overlay"` but classified `role: "other"` (an emoji-heavy
# exclamation doesn't cleanly read as "headline" to the model), and was
# silently dropped entirely - a genuine part of the creator's own
# caption, not disclaimer fine print, the role-gate's original intent.
# `surface` is now the sole inclusion signal (see `_eligible_blocks`);
# this map is only ever consulted for styling, with
# `_DEFAULT_HIERARCHY_FOR_UNMAPPED_ROLE` covering everything else
# (`other`, `disclaimer`, and any future role OCR might return) rather
# than excluding it.
_ROLE_TO_HIERARCHY = {
    "headline": "headline",
    "subheadline": "subhead",
    "price": "subhead",
    "cta": "cta",
}
_DEFAULT_HIERARCHY_FOR_UNMAPPED_ROLE = "subhead"

# hierarchy -> deterministic size only (see module docstring - every
# other styling concern, real bold typeface/stroke/centering/no
# background, is now a single unconditional treatment
# app.services.rendering_engine applies to every TextAsset, not a
# per-hierarchy design choice made here).
_HIERARCHY_STYLE = {
    "headline": {"size_class": "large"},
    "subhead": {"size_class": "medium"},
    "cta": {"size_class": "medium"},
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


def _is_packaging_text(text: str, packaging_text: list[str]) -> bool:
    normalized = text.strip().casefold()
    return any(normalized == candidate.strip().casefold() for candidate in packaging_text)


def _eligible_blocks(ocr_result: OCRResult | None, packaging_text: list[str]) -> list[dict]:
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): a real generation
    duplicated text that the base image generation already reproduces
    as part of the photographed scene - product packaging text AND,
    more broadly, other physical text like shelf price tags - by
    re-compositing it a second time as a marketing overlay. `role`
    alone can't tell "text a camera would have captured" apart from
    "text someone added on top of the photo afterward" (both can share
    a role like "headline"); only genuinely creator-added overlay text
    (a caption, a watermark) belongs to this module at all - anything
    physically in the scene is the base image generation's job to
    reproduce, never this pipeline's, and it's up to whichever
    `text_strategy` the user picked whether overlay text is reused
    verbatim, rewritten, or dropped.

    `block["surface"] == "overlay"` is OCR's own explicit classification
    of that distinction - the primary filter, and (real-world-diagnosed
    correction, see MIGRATION_PLAN.md) now the *only* role-related
    filter - `role` itself no longer gates inclusion, only styling (see
    `_ROLE_TO_HIERARCHY`'s own docstring for the real bug this fixes).
    A pre-migration OCRResult has no `surface` key at all;
    `.get("surface")` then returns `None`, which correctly excludes it
    (nothing to reuse yet), the same tri-state precedent this module
    already holds for OCRResults with no `bounding_box`.

    packaging_text (the product's own branding_text) is kept as a
    second, narrower line of defense specifically for packaging text -
    catches the case where OCR's own surface classification gets a
    genuinely packaging-printed block wrong, reusing the exact source
    of truth Stage 2 validation's `branding_text` field_check already
    compares against.
    """
    if ocr_result is None:
        return []
    return [
        block
        for block in ocr_result.structured_blocks_json
        if block.get("bounding_box")
        and block.get("surface") == "overlay"
        and not _is_packaging_text(block.get("text", ""), packaging_text)
    ]


def _merge_adjacent_overlay_blocks(blocks: list[dict]) -> list[dict]:
    """
    Real-world-diagnosed fix (Generate All follow-up, see
    MIGRATION_PLAN.md): a real caption ("Why would u pay £24 for
    this...") came back from OCR as two separate blocks - the source
    video's own on-screen caption had a line break, so OCR reported two
    spatially distinct text regions, same role, one almost directly
    beneath the other. Built as two independent TextAssets, the second
    ("this...") rendered as its own single-word line with no knowledge
    of the first - the exact "orphan word on its own line" the user
    flagged, except no single TextAsset's own wrapping could ever fix
    it, since the two words were never in the same string to begin
    with. Merges same-role blocks that are vertically adjacent (the gap
    between them is small relative to their own line height) and
    horizontally overlapping (a real continuation of the same caption,
    not an unrelated nearby element) into one combined block, in
    reading order (top to bottom), before any TextAsset is built -
    downstream wrapping then sees and rebalances the whole caption
    together.
    """
    ordered = sorted(blocks, key=lambda block: block["bounding_box"]["y_min"])
    merged: list[dict] = []
    for block in ordered:
        box = block["bounding_box"]
        if merged:
            prev = merged[-1]
            prev_box = prev["bounding_box"]
            same_role = prev["role"] == block["role"]
            line_height = prev_box["y_max"] - prev_box["y_min"]
            vertical_gap = box["y_min"] - prev_box["y_max"]
            close_enough = vertical_gap <= max(line_height, 0.02) * 1.5
            horizontally_overlaps = box["x_min"] < prev_box["x_max"] and prev_box["x_min"] < box["x_max"]
            if same_role and close_enough and horizontally_overlaps:
                merged[-1] = {
                    **prev,
                    "text": f"{prev['text']} {block['text']}",
                    "bounding_box": {
                        "x_min": min(prev_box["x_min"], box["x_min"]),
                        "y_min": prev_box["y_min"],
                        "x_max": max(prev_box["x_max"], box["x_max"]),
                        "y_max": box["y_max"],
                    },
                }
                continue
        merged.append(dict(block))
    return merged


def _text_asset_from_block(block: dict, wording: str) -> dict:
    hierarchy = _ROLE_TO_HIERARCHY.get(block["role"], _DEFAULT_HIERARCHY_FOR_UNMAPPED_ROLE)
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
        },
    }


def build_text_assets(
    text_strategy: str,
    ocr_result: OCRResult | None,
    *,
    text_generation_provider=None,
    packaging_text: list[str] | None = None,
) -> list[dict]:
    """
    Returns the list of TextAsset dicts the Rendering Engine should
    composite. `no_text` (and any slide with nothing eligible to
    reuse) returns `[]` - a real, valid outcome the Rendering Engine
    treats as a straight pass-through, not an error.

    packaging_text (real-world-diagnosed fix, see MIGRATION_PLAN.md and
    `_eligible_blocks`'s own docstring): the product's own
    branding_text (text physically printed on its packaging) - any OCR
    block whose text matches an entry here is excluded, regardless of
    its OCR-assigned role, since the base generated image already
    preserves it. `None`/`[]` (a slide with no resolved product, or a
    product with no current Lock Profile) skips this filter entirely -
    the same tri-state discipline this module already holds for
    OCR-less slides above.
    """
    if text_strategy not in TEXT_STRATEGIES:
        raise ValueError(f"Unknown text_strategy {text_strategy!r} - must be one of {sorted(TEXT_STRATEGIES)}")

    if text_strategy == TEXT_STRATEGY_NO_TEXT:
        return []

    blocks = _merge_adjacent_overlay_blocks(_eligible_blocks(ocr_result, packaging_text or []))
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
