"""
Source-style-aware rendering policy.

The incident this prevents: the compiler appended "This must look like a
real photograph" to EVERY prompt, the photorealism validator scored every
candidate against that same universal expectation, and the retry loop fed
"this is clearly an illustration rather than a real photograph" back to
the provider. For a slide whose source is deliberately an illustration,
all three were wrong in the same direction, and each retry pushed the
output further from the source.
"""

import pytest

from app.prompts.generation import GENERATION_COMPILER, compile_creative_intent
from app.services.source_style import (
    RenderingFamily,
    SourceStyle,
    classify_source_style,
)

ILLUSTRATED = {
    "visual_style": "Illustrative and informational",
    "graphic_style": "Digital illustration with a semi-realistic, hand-drawn feel",
}
PHOTOGRAPHIC = {
    "visual_style": "Candid, user-generated content (UGC) style retail snapshot",
    "graphic_style": "Photographic with a native digital text overlay",
}
RENDER = {"visual_style": "Clean product visual", "graphic_style": "3D render of the product"}
INFOGRAPHIC = {"visual_style": "Instructional infographic", "graphic_style": "Flat design icons"}


def test_classifies_the_incident_slide_as_illustration():
    """Slide 1 of incident e3fbf713 - the one that was told to become a photo."""
    result = classify_source_style(ILLUSTRATED)
    assert result.style is SourceStyle.EDITORIAL_ILLUSTRATION
    assert result.family is RenderingFamily.ILLUSTRATED
    assert result.is_confident
    assert result.evidence


@pytest.mark.parametrize(
    "fingerprint,expected",
    [
        (PHOTOGRAPHIC, RenderingFamily.PHOTOGRAPHIC),
        (ILLUSTRATED, RenderingFamily.ILLUSTRATED),
        (RENDER, RenderingFamily.RENDER),
        (INFOGRAPHIC, RenderingFamily.ILLUSTRATED),
    ],
)
def test_families_route_correctly(fingerprint, expected):
    assert classify_source_style(fingerprint).family is expected


def test_mixed_media_is_not_triggered_by_a_text_overlay():
    """
    Almost every slide in this product is "a photo with a text overlay",
    and composited typography is the Rendering Engine's job. If that
    counted as mixed media the category would be meaningless.
    """
    assert classify_source_style(PHOTOGRAPHIC).style is not SourceStyle.MIXED_MEDIA


def test_genuinely_mixed_imagery_is_detected():
    mixed = {
        "visual_style": "Illustrative and clean, with a focus on product demonstration",
        "graphic_style": "A mix of digital illustration and 3D rendering for the product",
    }
    assert classify_source_style(mixed).style is SourceStyle.MIXED_MEDIA


def test_no_evidence_reports_low_confidence_rather_than_guessing():
    result = classify_source_style({})
    assert not result.is_confident
    assert result.confidence == 0.0


# --- The safeguard the incident requires ----------------------------

_PHOTO_DEMANDS = [
    "must look like a real photograph",
    "not an illustration",
    "rather than a real photograph",
    "didn't look sufficiently realistic",
]


def _intent(fingerprint):
    return compile_creative_intent(
        {"composition": "a person at a desk"},
        source_style=classify_source_style(fingerprint),
    )


@pytest.mark.parametrize("fingerprint", [ILLUSTRATED, INFOGRAPHIC])
def test_an_illustrated_source_is_never_told_to_become_a_photograph(fingerprint):
    """
    THE safeguard. No generation prompt for an illustrated source may
    demand photographic realism - that instruction is what turned a
    faithful illustrated recreation into a rejected candidate, and then
    taught the retry loop to abandon the source style entirely.
    """
    intent = _intent(fingerprint).lower()
    for phrase in _PHOTO_DEMANDS:
        assert phrase not in intent, f"illustrated source was told: {phrase!r}"
    assert "remain an illustration" in intent


def test_a_photographic_source_still_demands_realism():
    """The counterpart - this must not become a licence for sloppy realism."""
    intent = _intent(PHOTOGRAPHIC).lower()
    assert "must look like a real photograph" in intent


def test_a_3d_source_is_judged_as_a_render():
    intent = _intent(RENDER).lower()
    assert "3d render" in intent
    assert "must look like a real photograph" not in intent


def test_unknown_style_falls_back_to_source_faithful_not_photographic():
    """
    With no evidence, asserting a medium would be a guess. Describing
    the source's own medium is always safe.
    """
    intent = compile_creative_intent({"composition": "x"}, source_style=classify_source_style({}))
    assert "must look like a real photograph" not in intent.lower()
    assert "match the visual medium" in intent.lower()


def test_every_rendering_family_has_a_registered_fragment():
    """A family with no fragment would silently fall back to photographic."""
    for name in (
        "render_photographic",
        "render_illustrated",
        "render_3d",
        "render_mixed",
        "render_source_faithful",
    ):
        assert name in GENERATION_COMPILER.fragments


def test_retry_openings_never_demand_a_change_of_medium():
    from app.prompts.generation import RETRY_REASON

    for key in ("style_illustrated", "style_render", "style_mixed"):
        text = RETRY_REASON.fragments[key].lower()
        for phrase in _PHOTO_DEMANDS:
            assert phrase not in text


# --- Transformation policy -------------------------------------------


def test_the_transformation_policy_is_explicit_not_emergent():
    """
    Before this existed, what to keep and what to change was whatever the
    creative-specification model happened to write that call. Across seven
    slides of one run the instructions ranged from "avoid copying the
    exact original character... pose" to "the person should visibly feel
    discomfort" to nothing at all - and two slides discarded the pose,
    which is the one thing that should be kept.
    """
    intent = compile_creative_intent({"composition": "a person at a desk"})

    assert "PRESERVE BEHAVIOURALLY" in intent
    assert "pose" in intent
    assert "MAKE NEW" in intent
    assert "facial identity" in intent
    assert "same creative concept, not as the same person" in intent


def test_the_policy_keeps_pose_and_changes_identity():
    """The two halves that must never be swapped."""
    intent = compile_creative_intent({"composition": "x"})
    preserve_block = intent[intent.index("PRESERVE BEHAVIOURALLY") : intent.index("MAKE NEW")]
    make_new_block = intent[intent.index("MAKE NEW") :]

    assert "pose" in preserve_block
    assert "body language" in preserve_block
    assert "facial identity" in make_new_block
    assert "hairstyle" in make_new_block
    assert "pose" not in make_new_block, "the pose must never be listed as something to change"


def test_the_policy_applies_on_every_prompt():
    """It is a product-wide rule, not something a spec model opts into."""
    for spec in ({"composition": "a"}, {"mood": "b"}, {}):
        assert "TRANSFORMATION POLICY" in compile_creative_intent(spec)


# --- Slideshow consensus ---------------------------------------------


def _c(fingerprint):
    return classify_source_style(fingerprint)


def test_a_lone_disagreeing_slide_becomes_mixed_not_flipped():
    """
    Incident e3fbf713 slide 2 is a hand-drawn illustration whose Creative
    Fingerprint confidently described it as "Photographic with subtle
    digital enhancements". Classified alone it drew the photographic
    criteria and its correctly-illustrated recreation was rejected for
    looking "more like a polished AI illustration than a real photograph"
    - while its siblings passed as illustrations.

    It becomes MIXED rather than being flipped to illustrated: flipping
    would be a second guess dressed as a rule, and would force a genuine
    product photo in an illustrated deck into the wrong criteria.
    """
    from app.services.source_style import apply_slideshow_consensus

    odd_one_out = _c(PHOTOGRAPHIC)
    siblings = [_c(ILLUSTRATED), _c(ILLUSTRATED), _c(ILLUSTRATED), _c(INFOGRAPHIC)]

    result = apply_slideshow_consensus(odd_one_out, siblings)

    assert result.style is SourceStyle.MIXED_MEDIA
    assert result.family is RenderingFamily.MIXED
    assert any("sibling slides read as" in e for e in result.evidence)
    assert result.secondary is SourceStyle.PHOTOGRAPHIC, "the original reading is kept"


def test_a_slide_agreeing_with_its_slideshow_is_untouched():
    from app.services.source_style import apply_slideshow_consensus

    own = _c(ILLUSTRATED)
    result = apply_slideshow_consensus(own, [_c(ILLUSTRATED), _c(ILLUSTRATED), _c(INFOGRAPHIC)])
    assert result is own


def test_a_genuinely_mixed_slideshow_leaves_every_slide_alone():
    """No majority means no override - product shots keep their criteria."""
    from app.services.source_style import apply_slideshow_consensus

    own = _c(PHOTOGRAPHIC)
    siblings = [_c(ILLUSTRATED), _c(ILLUSTRATED), _c(PHOTOGRAPHIC), _c(PHOTOGRAPHIC)]
    assert apply_slideshow_consensus(own, siblings) is own


def test_too_few_siblings_to_form_a_majority():
    from app.services.source_style import apply_slideshow_consensus

    own = _c(PHOTOGRAPHIC)
    assert apply_slideshow_consensus(own, [_c(ILLUSTRATED), _c(ILLUSTRATED)]) is own


def test_unconfident_siblings_do_not_vote():
    """A slide with no style evidence has no opinion to contribute."""
    from app.services.source_style import apply_slideshow_consensus

    own = _c(PHOTOGRAPHIC)
    siblings = [_c(ILLUSTRATED), _c({}), _c({}), _c({})]
    assert apply_slideshow_consensus(own, siblings) is own
