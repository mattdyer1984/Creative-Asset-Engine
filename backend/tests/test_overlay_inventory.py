"""
The specification may reword the original's overlay text. It may not invent
more of it.

case02's source carries exactly one overlay block - "All 5 books for the
price of 1 right now". The specification produced three: a headline, a
subhead, and "Tap the link before it's gone", a call to action that appears
nowhere in the original. `ocr` was already a declared dependency of that
stage; nothing read it.
"""

from __future__ import annotations

from app.prompts.generation import compile_creative_specification_prompt

FINGERPRINT = '{"tone": "deal-led"}'
CASE02_OVERLAY = ["All 5 books for the price of 1 right now"]


def _prompt(**kwargs):
    return compile_creative_specification_prompt(
        lock_profile_json='{"product": "book bundle"}',
        fingerprint_json=FINGERPRINT,
        **kwargs,
    )


def test_the_source_overlay_text_is_listed_verbatim():
    prompt = _prompt(overlay_blocks=CASE02_OVERLAY)
    assert '"All 5 books for the price of 1 right now"' in prompt


def test_inventing_extra_blocks_is_forbidden():
    prompt = _prompt(overlay_blocks=CASE02_OVERLAY)
    assert "Reproduce these lines of copy and no others" in prompt
    assert "do not split one line into several" in prompt


def test_rewording_is_still_allowed():
    """The recreation is not a copy - only the inventory is fixed."""
    prompt = _prompt(overlay_blocks=CASE02_OVERLAY)
    assert "You may reword a line" in prompt


def test_a_creative_with_no_overlay_text_gets_an_explicit_empty_instruction():
    prompt = _prompt(overlay_blocks=[])
    assert "has NO overlay WORDS" in prompt
    assert "Return an empty text_overlays array" in prompt


def test_an_empty_list_and_none_are_not_the_same_thing():
    """
    [] means the original genuinely has none. None means the caller did not
    look - an unmigrated caller must not silently suppress every overlay.
    """
    assert "NO overlay WORDS" in _prompt(overlay_blocks=[])
    unknown = _prompt(overlay_blocks=None)
    assert "NO overlay WORDS" not in unknown
    assert "Reproduce these lines of copy" not in unknown


def test_the_word_suggested_is_gone_from_the_focus_line():
    """It read as an invitation to write copy the original never had."""
    assert "suggested text overlays" not in _prompt(overlay_blocks=CASE02_OVERLAY)


def test_multiple_source_blocks_are_all_listed():
    prompt = _prompt(overlay_blocks=["Hook line", "Second line"])
    assert '"Hook line"' in prompt and '"Second line"' in prompt


# ---------------------------------------------------------------------------
# The inventory constrains COPY, not every overlaid element.
#
# The first wording said "reproduce THESE blocks and only these". The model
# read that as covering the pointing-emoji row too - which OCR does not
# record as text, so it was not on the list - and dropped it. Both candidates
# of that run came back with no pointer at all, even though the composition
# contract had it at [0.106, 0.895, 0.289, 0.953].
# ---------------------------------------------------------------------------


def test_non_text_affordances_are_explicitly_out_of_scope():
    prompt = _prompt(overlay_blocks=CASE02_OVERLAY)
    assert "WORDS ONLY" in prompt
    assert "pointing emoji" in prompt
    assert "If the original has them, keep them." in prompt


def test_an_empty_inventory_still_protects_the_pointer():
    """"No overlay words" must not read as "no overlay elements"."""
    prompt = _prompt(overlay_blocks=[])
    assert "NO overlay WORDS" in prompt
    assert "pointing emoji" in prompt


def test_the_constraint_is_stated_in_terms_of_copy():
    prompt = _prompt(overlay_blocks=CASE02_OVERLAY)
    assert "lines of copy" in prompt
