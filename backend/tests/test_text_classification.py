"""
Text classification against the benchmark set (ADR 0001 §4).

Every string here is real text from the eight gold-standard pairs. The
product rule is that baked-in text belongs to the creative and is preserved
by default; getting it backwards stripped designed typography and replaced
it with a generic caption style.
"""

import pytest

from app.services.text_classification import (
    AUTO_OVERRIDE_CONFIDENCE,
    TextClass,
    carries_platform_caption,
    classify_block,
)

CAPTION_PROJECTS = {
    "case1_weather": [
        {"text": "NOW WAY NOT AGAINNN\U0001f629", "surface": "overlay"},
        {"text": "Apparently it's only going to get hotter so please don't be paying...",
         "surface": "overlay"},
    ],
    "case2_books": [
        {"text": "All 5 books for the price of 1 right now", "surface": "overlay"},
        {"text": "\U0001f447\U0001f447\U0001f447", "surface": "overlay"},
    ],
    "case3_mini_ac": [
        {"text": "When this mini AC costs a fraction of them prices and does a job better...",
         "surface": "overlay"},
        {"text": "(Just add water & plug it in ✅)", "surface": "overlay"},
    ],
    "case8_fan_shelf": [
        {"text": "when ur paying £30 for this...", "surface": "overlay"},
        {"text": '16" Pedestal Fan', "surface": "physical"},
        {"text": "£30", "surface": "physical"},
    ],
}

DESIGNED_PROJECTS = {
    "case4_posture": [
        {"text": "1.", "surface": "overlay"},
        {"text": "Your upper back", "surface": "overlay"},
        {"text": "feels rounded", "surface": "overlay"},
        {"text": "You struggle to straighten up", "surface": "overlay"},
        {"text": "Shoulders keep falling forward", "surface": "overlay"},
    ],
    "case5_10_10_man": [
        {"text": "HOW TO BE A", "surface": "overlay"},
        {"text": "10/10 man", "surface": "overlay"},
    ],
    "case6_meal_prep": [
        {"text": "british meal prep \U0001f1ec\U0001f1e7", "surface": "overlay"},
        {"text": "vs", "surface": "overlay"},
        {"text": "japanese meal prep \U0001f1f0\U0001f1f7", "surface": "overlay"},
    ],
    "case7_gut_health": [
        {"text": "3 SIGNS OF", "surface": "overlay"},
        {"text": "BAD GUT HEALTH", "surface": "overlay"},
        {"text": "AND HOW TO SUPPORT IT", "surface": "overlay"},
        {"text": "BAD", "surface": "overlay"},
        {"text": "GOOD", "surface": "overlay"},
    ],
}


@pytest.mark.parametrize("case", sorted(CAPTION_PROJECTS))
def test_caption_projects_are_detected(case):
    assert carries_platform_caption(CAPTION_PROJECTS[case]) is True


@pytest.mark.parametrize("case", sorted(DESIGNED_PROJECTS))
def test_designed_projects_are_never_masked(case):
    """
    The regression that motivated ADR 0001. Masking a designed creative
    strips typography that nothing can currently reconstruct.
    """
    assert carries_platform_caption(DESIGNED_PROJECTS[case]) is False


def test_emoji_alone_never_decides():
    """
    Benchmark 6 uses flag emoji as part of its designed comparison
    typography. An earlier version scored it a caption purely on the emoji
    and would have masked the design away.
    """
    block = {"text": "british meal prep \U0001f1ec\U0001f1e7", "surface": "overlay"}
    assert classify_block(block).text_class is TextClass.DESIGNED_TYPOGRAPHY


def test_physical_text_is_product_native_regardless_of_wording():
    """Product-native text is owned by Product Lock (ADR 0001 §6)."""
    block = {"text": "when ur paying £30 for this...", "surface": "physical"}
    result = classify_block(block)
    assert result.text_class is TextClass.PRODUCT_NATIVE
    assert result.is_baked_in


def test_unclassifiable_text_is_preserved_not_removed():
    """Preserving is the recoverable failure (ADR 0001 D7)."""
    result = classify_block({"text": "Marble", "surface": "overlay"})
    assert result.is_baked_in


def test_a_weak_caption_signal_does_not_authorise_masking():
    """
    carries_platform_caption requires confidence above the auto-override
    band, not merely a winning class - erasing text from the reference is
    not something a marginal signal should trigger.
    """
    blocks = [{"text": "Our range", "surface": "overlay"}]
    result = classify_block(blocks[0])
    if result.text_class is TextClass.PLATFORM_CAPTION:
        assert result.confidence < AUTO_OVERRIDE_CONFIDENCE
    assert carries_platform_caption(blocks) is False


# --- Gaps the benchmark harness exposed (WP-0.2) ---------------------


def test_an_emoji_only_block_is_a_caption():
    """
    A row of pointing hands is a caption gesture, never designed
    typography. This is the one case where emoji decide alone, and it is
    safe precisely because there is no typography to destroy.
    """
    result = classify_block({"text": "\U0001f447\U0001f447\U0001f447", "surface": "overlay"})
    assert result.text_class is TextClass.PLATFORM_CAPTION
    assert not result.is_baked_in


def test_elongated_spelling_reads_as_spoken_emphasis():
    """
    "NOW WAY NOT AGAINNN" scored zero signals before this and defaulted to
    preserved. Designed typography does not stretch its own words.
    """
    result = classify_block({"text": "NOW WAY NOT AGAINNN\U0001f629", "surface": "overlay"})
    assert result.text_class is TextClass.PLATFORM_CAPTION


def test_screen_and_signage_text_is_baked_in():
    """
    Environmental text - a weather map, a shelf sign - is displayed on a
    real object the camera photographed, so OCR reports it physical and it
    belongs to the creative.
    """
    result = classify_block({"text": "Edinburgh 23", "surface": "physical"})
    assert result.is_baked_in


def test_designed_typography_is_still_protected_after_the_new_signals():
    """The new caption signals must not start eating designed typography."""
    for text in ("HOW TO BE A", "BAD GUT HEALTH", "3 SIGNS OF", "feels rounded"):
        assert classify_block({"text": text, "surface": "overlay"}).is_baked_in
