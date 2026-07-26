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
AUTO_OVERRIDE_CONFIDENCE = 0.80
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

    if caption_score > editorial_score:
        return BlockClassification(
            TextClass.PLATFORM_CAPTION, round(caption_score / total, 3), reasons
        )
    return BlockClassification(
        TextClass.DESIGNED_TYPOGRAPHY, round(editorial_score / total, 3), reasons
    )


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
