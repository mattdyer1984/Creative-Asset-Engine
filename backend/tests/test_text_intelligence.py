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
    "bounding_box": {"x_min": 0.05, "y_min": 0.05, "x_max": 0.9, "y_max": 0.2},
}
_CTA_BLOCK = {
    "text": "SHOP NOW",
    "role": "cta",
    "bounding_box": {"x_min": 0.05, "y_min": 0.85, "x_max": 0.3, "y_max": 0.95},
}
_LOGO_BLOCK = {
    "text": "BELLA VITA",
    "role": "logo_text",
    "bounding_box": {"x_min": 0.4, "y_min": 0.4, "x_max": 0.6, "y_max": 0.45},
}
_NO_BBOX_BLOCK = {"text": "Old-style block", "role": "headline"}


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
    assert assets[0]["styling"] == {"size_class": "large", "weight": "bold", "render_style": "scrim"}

    assert assets[1]["wording"] == "SHOP NOW"
    assert assets[1]["hierarchy"] == "cta"
    assert assets[1]["semantic_role"] == "cta"
    assert assets[1]["styling"]["render_style"] == "badge"


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
        def generate(self, prompt_spec, response_schema):
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
        def generate(self, prompt_spec, response_schema):
            return {"rewritten": ["only one"]}

    with pytest.raises(ValueError, match="must be exactly one per block"):
        build_text_assets(TEXT_STRATEGY_AI_REWRITE, ocr, text_generation_provider=_BadFakeTextProvider())
