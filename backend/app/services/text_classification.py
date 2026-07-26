"""
Text classification (ADR 0001 §4, §12).

**The product rule this serves.** Baked-in text belongs to the creative and
is preserved by default. Overlay text belongs to the post and is optional
according to the user's decision. Getting this the wrong way round is what
produced output far below the source: designed editorial typography - a red
numeral, a serif headline, a red italic subhead, red-bulleted lists - was
stripped from the image and replaced with the generic bold-white-with-black-
stroke caption style.

**Preservation is the safe failure.** Keeping text that could have been
removed is recoverable in one click. Removing text that should have been
kept destroys the creative and cannot be recovered from the output. Every
threshold here is therefore biased toward preserving, and an uncertain block
is preserved and surfaced rather than silently decided (ADR 0001 D7).

**Scope note.** This module currently implements the WP-0.4 interim gate:
enough classification to stop designed typography being masked away. WP-1.1
replaces the heuristics below with project-level mode plus per-block override
and real confidence thresholds; the vocabulary and the public shape are
already the WP-1.1 ones so that lands as an extension rather than a rewrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class TextClass(StrEnum):
    """ADR 0001 §4. `environmental` and `product_native` are both baked-in."""

    PRODUCT_NATIVE = "product_native"
    DESIGNED_TYPOGRAPHY = "designed_typography"
    PLATFORM_CAPTION = "platform_caption"
    ENVIRONMENTAL = "environmental"


#: Classes that belong to the creative and are preserved by default (§4.1).
BAKED_IN_CLASSES = frozenset(
    {TextClass.PRODUCT_NATIVE, TextClass.DESIGNED_TYPOGRAPHY, TextClass.ENVIRONMENTAL}
)

# Confidence bands, ADR 0001 §12.2.
#
# O3 re-scaled these. Confidence used to saturate at exactly 1.0 whenever
# signals fired on only one side, which is almost every block, so 0.80 was
# reachable by a single weak match. Now that confidence carries evidence
# WEIGHT as well as agreement, the same numbers mean different things:
# one strong signal (3.5) scores 0.70, two moderate ones 0.77, a lone weak
# one 0.40. The bands are moved so behaviour is preserved rather than
# silently tightened by a change of scale.
#
# Derived from the signal table, not chosen: 0.65 is just below one strong
# signal, so an unambiguous `#fyp` still auto-overrides the project default.
AUTO_OVERRIDE_CONFIDENCE = 0.65
REVIEW_CONFIDENCE = 0.55

_EMOJI = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff⬀-⯿]"
)

# Signals that the wording is a person talking, not a designer typesetting.
_CONVERSATIONAL = [
    (re.compile(r"\.\.\.\s*$"), 2.0, "trails off with an ellipsis"),
    (re.compile(r"\b(ur|u|rn|ngl|fr|tbh|idk|omg|lmao)\b", re.I), 2.5, "text-speak"),
    (re.compile(r"\bwhen (this|ur|you|i|my)\b", re.I), 2.0, "'when …' caption opener"),
    (re.compile(r"\b(apparently|honestly|literally|basically)\b", re.I), 1.5, "hedging adverb"),
    (re.compile(r"^\(.*\)$"), 1.5, "parenthetical aside"),
    (re.compile(r"\b(i|me|my|we|our)\b", re.I), 1.0, "first person"),
    (re.compile(r"\bright now\b|\bso please\b|\bdon'?t be\b", re.I), 1.5, "spoken phrasing"),
    # Elongation is a spoken-emphasis device ("AGAINNN", "soooo"). Designed
    # typography does not stretch its own words.
    (re.compile(r"([A-Za-z])\1{2,}"), 2.0, "elongated spelling"),
    # Platform furniture. These are the least ambiguous signals there are:
    # a hashtag or an @mention is addressed to the feed, not to the reader
    # of the creative, and no designed editorial layout contains one. They
    # are weighted to decide on their own, unlike emoji - a designer may use
    # a flag emoji as part of a comparison, but not `#fyp`.
    (re.compile(r"(?:^|\s)#\w"), 3.5, "hashtag - addressed to the platform"),
    (re.compile(r"(?:^|\s)@\w"), 3.0, "@mention"),
    (re.compile(r"^\s*(pov|povs)\s*:", re.I), 3.5, "'pov:' caption opener"),
    (re.compile(r"^\s*(me|him|her|them|us)\s+when\b", re.I), 3.0, "'me when' caption opener"),
    (re.compile(r"\b(no because|not me|the way)\b", re.I), 2.0, "caption idiom"),
]

# Signals that this is typeset as part of the design.
_EDITORIAL = [
    (re.compile(r"^\s*\d+\s*[.)]\s*$"), 3.0, "standalone list numeral"),
    (re.compile(r"^\s*\d+\s*[.)]\s"), 2.0, "numbered heading"),
    (re.compile(r"^[A-Z][A-Z\s&/'-]{3,}$"), 2.0, "all-caps display line"),
    (re.compile(r"^(vs\.?|versus)$", re.I), 3.0, "comparison connective"),
    (re.compile(r"^(bad|good|before|after|pros?|cons?)$", re.I), 2.5, "comparison label"),
    (re.compile(r"^\d+\s+(signs?|ways?|reasons?|steps?|tips?)\b", re.I), 2.5, "listicle headline"),
]


#: Evidence weight at which the strength term reaches 0.5. Set from the
#: signal table itself: the weakest single signal is 1.0 and the strongest
#: is 3.5, so a lone weak signal lands near 0.4 and a strong one near 0.6 -
#: which is the honest reading of each.
_EVIDENCE_MIDPOINT = 1.5


def _confidence(winning_score: float, total_score: float) -> float:
    """
    How much to trust this classification, as agreement AND weight.

    O3. Phase F measured 76 of 79 decisions at exactly 1.0 and the medium
    band empty, so confidence discriminated nothing. The cause was
    mechanical: confidence was `winner / (winner + loser)`, and because
    signals from only one side fire in almost every real block, the loser was
    0 and the ratio was exactly 1.

    That number answered "did anything contradict this?" - not "how sure are
    we?". A block matching one weak pattern with nothing against it is not
    the same as one matching four strong patterns, and the old formula
    scored both 1.0.

    Two independent terms, multiplied because both must hold:

      agreement  the winner's share of all fired signal weight
      strength   how much evidence fired at all, saturating

    Neither alone is enough: agreement alone saturates (the old bug), and
    strength alone would call a strongly contested block confident.
    """
    if total_score <= 0:
        return 0.0
    agreement = winning_score / total_score
    strength = total_score / (total_score + _EVIDENCE_MIDPOINT)
    return round(agreement * strength, 3)


@dataclass(frozen=True)
class BlockClassification:
    text_class: TextClass
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def is_baked_in(self) -> bool:
        return self.text_class in BAKED_IN_CLASSES

    @property
    def needs_review(self) -> bool:
        """Below this, the default applies but the user is told (§12.2)."""
        return self.confidence < REVIEW_CONFIDENCE


def classify_block(block: dict) -> BlockClassification:
    """
    Classify one OCR block.

    `surface == "physical"` short-circuits: OCR already established the text
    is printed on a real object the camera photographed, and that is decided
    by looking at the pixels rather than at the wording. Product-native text
    is owned by Product Lock (ADR 0001 §6), never by this module.
    """
    if block.get("surface") == "physical":
        return BlockClassification(
            TextClass.PRODUCT_NATIVE, 1.0, ["OCR reports the text is on a physical object"]
        )

    text = (block.get("text") or "").strip()
    if not text:
        return BlockClassification(TextClass.DESIGNED_TYPOGRAPHY, 0.0, ["no text to judge"])

    caption_score = 0.0
    editorial_score = 0.0
    reasons: list[str] = []

    for pattern, weight, why in _CONVERSATIONAL:
        if pattern.search(text):
            caption_score += weight
            reasons.append(f"caption: {why}")

    for pattern, weight, why in _EDITORIAL:
        if pattern.search(text):
            editorial_score += weight
            reasons.append(f"editorial: {why}")

    # Emoji lean toward a caption but must NEVER decide alone. Benchmark 6
    # ("british meal prep 🇬🇧 vs japanese meal prep 🇰🇷") is designed
    # comparison typography that uses flag emoji as part of its system; an
    # earlier version of this function scored it as a caption purely on the
    # emoji and would have masked the design away. Emoji therefore only
    # count once some other caption signal has already fired.
    has_emoji = bool(_EMOJI.search(text))

    # A block that is ONLY emoji is never designed typography - a row of
    # pointing hands is a caption gesture. This is the one case where emoji
    # decide on their own, and it is safe precisely because there is no
    # typography to destroy.
    if has_emoji and not _EMOJI.sub("", text).strip():
        return BlockClassification(
            TextClass.PLATFORM_CAPTION, 1.0, ["caption: emoji-only block"]
        )

    if has_emoji and caption_score > 0:
        caption_score += 1.0
        reasons.append("caption: contains emoji")
    elif has_emoji:
        reasons.append("emoji present but not decisive on its own")

    # Length is measured on the words, not the decoration - trailing flags or
    # a pointing hand would otherwise push a three-word label out of the
    # label-length band.
    words = len(_EMOJI.sub("", text).split())
    if words >= 9:
        caption_score += 1.0
        reasons.append("caption: sentence-length copy")
    elif words <= 3:
        editorial_score += 1.0
        reasons.append("editorial: label-length copy")

    total = caption_score + editorial_score
    if total == 0:
        # Nothing to go on. Default to the creative's own text, because
        # preserving is the recoverable failure.
        return BlockClassification(
            TextClass.DESIGNED_TYPOGRAPHY, 0.0, ["no distinguishing signals - preserving by default"]
        )

    winner, score = (
        (TextClass.PLATFORM_CAPTION, caption_score)
        if caption_score > editorial_score
        else (TextClass.DESIGNED_TYPOGRAPHY, editorial_score)
    )
    return BlockClassification(winner, _confidence(score, total), reasons)


def classify_blocks(blocks: list[dict] | None) -> list[BlockClassification]:
    return [classify_block(block) for block in blocks or []]


def carries_platform_caption(blocks: list[dict] | None) -> bool:
    """
    Does this creative carry a genuine platform caption?

    Used by the WP-0.4 gate to decide whether masking the reference image is
    safe. Requires a block classified as a caption ABOVE the auto-override
    band - not merely the winning class. A weak caption signal is not grounds
    for erasing text from the reference, because the cost of being wrong is
    destroying designed typography with no way to reconstruct it yet.
    """
    return any(
        classification.text_class is TextClass.PLATFORM_CAPTION
        and classification.confidence >= AUTO_OVERRIDE_CONFIDENCE
        for classification in classify_blocks(blocks)
    )
