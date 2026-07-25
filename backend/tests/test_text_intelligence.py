"""
Unit tests for app.services.text_intelligence (Phase 10.8 of AI
Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §9). Plain dicts/OCRResult only - no real provider call
for reuse_original/no_text; ai_rewrite uses a small local fake.
"""

import pytest

from app.models.ocr_result import OCRResult
from app.services.text_intelligence import (
    TEXT_STRATEGY_AI_REWRITE,
    TEXT_STRATEGY_NO_TEXT,
    TEXT_STRATEGY_REUSE_ORIGINAL,
    build_text_assets,
)


def _ocr_result(blocks: list[dict]) -> OCRResult:
    return OCRResult(raw_text="", structured_blocks_json=blocks, analysis_run_id="fake-run-id")


_HEADLINE_BLOCK = {
    "text": "SMELL LIKE YOU MEAN IT",
    "role": "headline",
    "surface": "overlay",
    "bounding_box": {"x_min": 0.05, "y_min": 0.05, "x_max": 0.9, "y_max": 0.2},
}
_CTA_BLOCK = {
    "text": "SHOP NOW",
    "role": "cta",
    "surface": "overlay",
    "bounding_box": {"x_min": 0.05, "y_min": 0.85, "x_max": 0.3, "y_max": 0.95},
}
_LOGO_BLOCK = {
    "text": "BELLA VITA",
    "role": "logo_text",
    "surface": "physical",
    "bounding_box": {"x_min": 0.4, "y_min": 0.4, "x_max": 0.6, "y_max": 0.45},
}
_NO_BBOX_BLOCK = {"text": "Old-style block", "role": "headline", "surface": "overlay"}
_PHYSICAL_PRICE_BLOCK = {
    "text": "£25",
    "role": "price",
    "surface": "physical",
    "bounding_box": {"x_min": 0.05, "y_min": 0.78, "x_max": 0.15, "y_max": 0.82},
}


def test_no_text_returns_empty_regardless_of_ocr_content():
    ocr = _ocr_result([_HEADLINE_BLOCK, _CTA_BLOCK])
    assert build_text_assets(TEXT_STRATEGY_NO_TEXT, ocr) == []


def test_no_ocr_result_returns_empty():
    assert build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, None) == []


def test_unknown_strategy_raises():
    with pytest.raises(ValueError, match="Unknown text_strategy"):
        build_text_assets("literally_anything_else", None)


def test_reuse_original_builds_one_text_asset_per_eligible_block():
    ocr = _ocr_result([_HEADLINE_BLOCK, _CTA_BLOCK, _LOGO_BLOCK])
    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert len(assets) == 2  # logo_text excluded - product packaging, not a marketing overlay
    assert assets[0]["wording"] == "SMELL LIKE YOU MEAN IT"
    assert assets[0]["hierarchy"] == "headline"
    assert assets[0]["semantic_role"] == "hook"
    assert assets[0]["positioning"] == {"x": 0.05, "y": 0.05, "width": pytest.approx(0.85)}
    assert assets[0]["styling"] == {"size_class": "large"}

    assert assets[1]["wording"] == "SHOP NOW"
    assert assets[1]["hierarchy"] == "cta"
    assert assets[1]["semantic_role"] == "cta"
    assert assets[1]["styling"] == {"size_class": "medium"}


def test_reuse_original_skips_blocks_with_no_bounding_box():
    """A pre-Phase-10.8 OCRResult has no positions to reuse - tri-state, not an error."""
    ocr = _ocr_result([_NO_BBOX_BLOCK, _CTA_BLOCK])
    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert len(assets) == 1
    assert assets[0]["wording"] == "SHOP NOW"


def test_ai_rewrite_requires_a_provider():
    ocr = _ocr_result([_HEADLINE_BLOCK])
    with pytest.raises(ValueError, match="requires a text_generation_provider"):
        build_text_assets(TEXT_STRATEGY_AI_REWRITE, ocr)


def test_ai_rewrite_replaces_wording_but_keeps_position_and_hierarchy():
    ocr = _ocr_result([_HEADLINE_BLOCK, _CTA_BLOCK])

    class _FakeTextProvider:
        def generate(self, prompt_spec, response_schema, *, usage_sink=None):
            assert "SMELL LIKE YOU MEAN IT" in prompt_spec["prompt"]
            assert "SHOP NOW" in prompt_spec["prompt"]
            return {"rewritten": ["WEAR CONFIDENCE", "BUY TODAY"]}

    assets = build_text_assets(TEXT_STRATEGY_AI_REWRITE, ocr, text_generation_provider=_FakeTextProvider())

    assert [a["wording"] for a in assets] == ["WEAR CONFIDENCE", "BUY TODAY"]
    assert assets[0]["hierarchy"] == "headline"
    assert assets[0]["positioning"]["x"] == 0.05


def test_ai_rewrite_raises_on_count_mismatch():
    ocr = _ocr_result([_HEADLINE_BLOCK, _CTA_BLOCK])

    class _BadFakeTextProvider:
        def generate(self, prompt_spec, response_schema, *, usage_sink=None):
            return {"rewritten": ["only one"]}

    with pytest.raises(ValueError, match="must be exactly one per block"):
        build_text_assets(TEXT_STRATEGY_AI_REWRITE, ocr, text_generation_provider=_BadFakeTextProvider())


# --- packaging_text exclusion (real-world-diagnosed fix, see MIGRATION_PLAN.md) ---


def test_reuse_original_excludes_blocks_matching_packaging_text():
    """
    Real bug: OCR tagged packaging-printed text ("STARTS WHITENING FROM
    DAY 1*") as role="headline" - already preserved on the product by
    Product Lock's branding_text, so re-compositing it as a marketing
    overlay duplicated it. Filtering against the product's own
    branding_text list catches this even when OCR's role tagging gets
    it wrong.
    """
    packaging_block = {
        "text": "STARTS WHITENING FROM DAY 1*",
        "role": "headline",
        "surface": "overlay",  # OCR's own surface classification got this one wrong too - the real case
        "bounding_box": {"x_min": 0.4, "y_min": 0.45, "x_max": 0.6, "y_max": 0.51},
    }
    ocr = _ocr_result([_HEADLINE_BLOCK, packaging_block, _CTA_BLOCK])

    assets = build_text_assets(
        TEXT_STRATEGY_REUSE_ORIGINAL, ocr, packaging_text=["Colgate", "STARTS WHITENING FROM DAY 1*"]
    )

    wordings = [a["wording"] for a in assets]
    assert wordings == ["SMELL LIKE YOU MEAN IT", "SHOP NOW"]


def test_packaging_text_match_is_case_and_whitespace_insensitive():
    packaging_block = {
        "text": "  starts whitening from day 1*  ",
        "role": "headline",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.4, "y_min": 0.45, "x_max": 0.6, "y_max": 0.51},
    }
    ocr = _ocr_result([packaging_block])

    assets = build_text_assets(
        TEXT_STRATEGY_REUSE_ORIGINAL, ocr, packaging_text=["STARTS WHITENING FROM DAY 1*"]
    )

    assert assets == []


def test_no_packaging_text_excludes_nothing():
    ocr = _ocr_result([_HEADLINE_BLOCK, _CTA_BLOCK])

    assert build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr, packaging_text=None) == build_text_assets(
        TEXT_STRATEGY_REUSE_ORIGINAL, ocr, packaging_text=[]
    )
    assert len(build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr, packaging_text=[])) == 2


# --- surface classification (real-world-diagnosed fix, see MIGRATION_PLAN.md) ---


def test_reuse_original_excludes_physical_price_tags_even_with_an_eligible_role():
    """
    Real bug: shelf price tags are physically part of the photographed
    scene (the base image generation already reproduces them) but OCR
    tags them role="price", which this module's own vocabulary
    otherwise treats as overlay-eligible. surface="physical" must
    exclude them regardless of role.
    """
    ocr = _ocr_result([_HEADLINE_BLOCK, _PHYSICAL_PRICE_BLOCK])

    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert [a["wording"] for a in assets] == ["SMELL LIKE YOU MEAN IT"]


def test_reuse_original_excludes_blocks_with_no_surface_field():
    """
    Pre-migration OCRResult data has no `surface` key at all - tri-state,
    same precedent as a missing bounding_box: nothing to reuse yet, not
    an error.
    """
    old_style_block = {
        "text": "SHOP NOW",
        "role": "cta",
        "bounding_box": {"x_min": 0.05, "y_min": 0.85, "x_max": 0.3, "y_max": 0.95},
    }
    ocr = _ocr_result([old_style_block])

    assert build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr) == []


def test_reuse_original_keeps_genuine_overlay_text():
    ocr = _ocr_result([_HEADLINE_BLOCK, _CTA_BLOCK, _PHYSICAL_PRICE_BLOCK])

    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert [a["wording"] for a in assets] == ["SMELL LIKE YOU MEAN IT", "SHOP NOW"]


def test_reuse_original_includes_an_overlay_block_with_an_unrecognized_role():
    """
    Real bug, reported live: a real caption's third line ("what have
    they done😭😭😭") came back from OCR correctly marked
    surface="overlay" but classified role="other" (an emoji-heavy
    exclamation doesn't cleanly read as "headline" to the model) - it
    was silently dropped entirely, since inclusion used to require
    role to be one of headline/subheadline/price/cta. `surface` alone
    must now be sufficient for inclusion; an unrecognized role should
    only affect styling (a sensible default hierarchy), never whether
    the block appears at all.
    """
    other_role_overlay = {
        "text": "what have they done😭😭😭",
        "role": "other",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.228, "y_min": 0.601, "x_max": 0.767, "y_max": 0.627},
    }
    ocr = _ocr_result([_HEADLINE_BLOCK, other_role_overlay])

    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert [a["wording"] for a in assets] == ["SMELL LIKE YOU MEAN IT", "what have they done😭😭😭"]
    assert assets[1]["styling"]["size_class"] == "medium"  # the default fallback hierarchy ("subhead")


# --- _merge_adjacent_overlay_blocks (real-world-diagnosed fix, see MIGRATION_PLAN.md) ---


def test_reuse_original_merges_a_caption_split_across_two_adjacent_ocr_blocks():
    """
    Real bug, reported live: the exact real caption "Why would u pay
    £24 for this..." came back from OCR as two separate blocks (the
    source video's own on-screen caption had a line break) - built as
    two independent TextAssets, "this..." rendered alone on its own
    line with no knowledge of the first block. These are the real
    bounding boxes from that report.
    """
    first = {
        "text": "Why would u pay £24 for",
        "role": "headline",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.163, "y_min": 0.63, "x_max": 0.866, "y_max": 0.672},
    }
    second = {
        "text": "this...",
        "role": "headline",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.449, "y_min": 0.686, "x_max": 0.587, "y_max": 0.728},
    }
    ocr = _ocr_result([first, second])

    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert len(assets) == 1
    assert assets[0]["wording"] == "Why would u pay £24 for this..."
    assert assets[0]["positioning"] == {"x": 0.163, "y": 0.63, "width": pytest.approx(0.866 - 0.163)}


def test_merge_leaves_unrelated_same_role_blocks_separate():
    """Far apart vertically, same role (headline + cta from the shared fixtures) - must not merge."""
    ocr = _ocr_result([_HEADLINE_BLOCK, _CTA_BLOCK])

    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert len(assets) == 2


def test_merge_does_not_combine_blocks_with_no_horizontal_overlap():
    """Vertically adjacent, same role, but side-by-side (e.g. two independent captions stacked by
    coincidence) - no horizontal overlap means they aren't a continuation of the same caption."""
    first = {
        "text": "Left caption",
        "role": "headline",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.0, "y_min": 0.5, "x_max": 0.2, "y_max": 0.55},
    }
    second = {
        "text": "Right caption",
        "role": "headline",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.6, "y_min": 0.55, "x_max": 0.9, "y_max": 0.6},
    }
    ocr = _ocr_result([first, second])

    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert [a["wording"] for a in assets] == ["Left caption", "Right caption"]


def test_merge_does_not_combine_blocks_of_different_roles():
    headline = {
        "text": "Big headline",
        "role": "headline",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.1, "y_min": 0.5, "x_max": 0.9, "y_max": 0.55},
    }
    cta = {
        "text": "Shop now",
        "role": "cta",
        "surface": "overlay",
        "bounding_box": {"x_min": 0.1, "y_min": 0.56, "x_max": 0.9, "y_max": 0.6},
    }
    ocr = _ocr_result([headline, cta])

    assets = build_text_assets(TEXT_STRATEGY_REUSE_ORIGINAL, ocr)

    assert [a["wording"] for a in assets] == ["Big headline", "Shop now"]
