"""
Source style classification.

**Why this exists.** The generation compiler used to append one
unconditional instruction to every prompt - "This must look like a real
photograph, not an illustration, painting, 3D render, or cartoon" - and
the photorealism validator scored every candidate against that same
universal expectation. For an illustrated source that is not a quality
bar, it is a contradiction: analysis correctly reported "Digital
illustration with a semi-realistic, hand-drawn feel", the compiler then
demanded the opposite, and the validator failed the candidate for
obeying the analysis instead of the default. The retry loop then fed
"this is clearly an illustration rather than a real photograph" back to
the provider, pushing each attempt further from the source.

**Deliberately deterministic, and deliberately not a new AI call.** The
style has already been classified - twice - by Creative Fingerprint
(`visual_style`, `graphic_style`) and Scene Intelligence. Asking another
model to name the style again would invite a third opinion that
contradicts the first two, which is the failure mode this module exists
to remove. So this reads what those stages already said and maps it,
in code, to a rendering family.

**Confidence is reported, never guessed around.** When the evidence is
weak the classification says so, and callers fall back to the
source-faithful behaviour (describe the style as analysed) rather than
asserting a mode the evidence does not support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class SourceStyle(StrEnum):
    PHOTOGRAPHIC = "photographic"
    COMMERCIAL_PRODUCT_PHOTOGRAPHY = "commercial_product_photography"
    RENDER_3D = "render_3d"
    EDITORIAL_ILLUSTRATION = "editorial_illustration"
    VECTOR_INFOGRAPHIC = "vector_infographic"
    CARTOON = "cartoon"
    MIXED_MEDIA = "mixed_media"


class RenderingFamily(StrEnum):
    """Which validator and which prompt wording apply."""

    PHOTOGRAPHIC = "photographic"
    ILLUSTRATED = "illustrated"
    RENDER = "render"
    MIXED = "mixed"


FAMILY_OF: dict[SourceStyle, RenderingFamily] = {
    SourceStyle.PHOTOGRAPHIC: RenderingFamily.PHOTOGRAPHIC,
    SourceStyle.COMMERCIAL_PRODUCT_PHOTOGRAPHY: RenderingFamily.PHOTOGRAPHIC,
    SourceStyle.RENDER_3D: RenderingFamily.RENDER,
    SourceStyle.EDITORIAL_ILLUSTRATION: RenderingFamily.ILLUSTRATED,
    SourceStyle.VECTOR_INFOGRAPHIC: RenderingFamily.ILLUSTRATED,
    SourceStyle.CARTOON: RenderingFamily.ILLUSTRATED,
    SourceStyle.MIXED_MEDIA: RenderingFamily.MIXED,
}

# Signals are matched against the fingerprint's own words. Weighted
# because they are not equally decisive: "hand-drawn" settles the
# question, "clean" does not.
_SIGNALS: dict[SourceStyle, list[tuple[str, float]]] = {
    SourceStyle.EDITORIAL_ILLUSTRATION: [
        (r"\bhand[- ]drawn\b", 3.0),
        (r"\billustrat(?:ion|ive|ed)\b", 2.5),
        (r"\bdrawn\b", 1.5),
        (r"\bline art\b", 2.0),
        (r"\beditorial illustration\b", 3.0),
        (r"\b2d\b", 1.0),
    ],
    SourceStyle.VECTOR_INFOGRAPHIC: [
        (r"\bvector\b", 2.5),
        (r"\binfographic\b", 2.5),
        (r"\bflat design\b", 2.5),
        (r"\bdiagram\b", 1.5),
        (r"\biconograph|(?<!\w)icons?\b", 1.0),
        (r"\bui/?ux|interface (?:mockup|simulation|reproduction)|skeuomorphic\b", 2.5),
        (r"\bscreenshot\b", 2.0),
    ],
    SourceStyle.CARTOON: [
        (r"\bcartoon\b", 3.0),
        (r"\banimated\b", 2.0),
        (r"\banime\b", 3.0),
        (r"\bcomic\b", 2.0),
    ],
    SourceStyle.RENDER_3D: [
        (r"\b3d render|3d[- ]render(?:ing|ed)?\b", 3.0),
        (r"\bcgi\b", 2.5),
        (r"\brendered?\b", 1.5),
    ],
    SourceStyle.COMMERCIAL_PRODUCT_PHOTOGRAPHY: [
        (r"\bproduct photograph", 3.0),
        (r"\bstudio\b", 1.5),
        (r"\bpolished\b", 1.5),
        (r"\bpremium editorial\b", 2.0),
        (r"\bcommercial\b", 1.5),
        (r"\bproduct[- ]ad\b", 1.5),
    ],
    SourceStyle.PHOTOGRAPHIC: [
        (r"\bphotorealistic\b", 2.5),
        (r"\bphotographic\b", 2.5),
        (r"\bphotography\b", 2.0),
        (r"\bphoto\b", 2.0),
        (r"\bugc\b", 2.0),
        (r"\buser[- ]generated\b", 2.0),
        (r"\bcandid\b", 1.5),
        (r"\bsnapshot\b", 1.5),
        (r"\bselfie\b", 2.0),
        (r"\bsmartphone[- ]shot|phone[- ]camera\b", 2.0),
    ],
}

# A source is only "mixed media" when its IMAGERY genuinely combines
# families. Nearly every slide in this product is "a photo with a text
# overlay", and composited typography is handled by the Rendering
# Engine - counting it as mixed media would make the category useless.
_MIXED_THRESHOLD_RATIO = 0.65
_LOW_CONFIDENCE = 0.45


@dataclass(frozen=True)
class StyleClassification:
    style: SourceStyle
    confidence: float
    evidence: list[str] = field(default_factory=list)
    secondary: SourceStyle | None = None
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def family(self) -> RenderingFamily:
        return FAMILY_OF[self.style]

    @property
    def is_confident(self) -> bool:
        return self.confidence >= _LOW_CONFIDENCE

    @property
    def is_photographic(self) -> bool:
        return self.family is RenderingFamily.PHOTOGRAPHIC


def classify_source_style(
    fingerprint: dict | None, scene_regions: list[dict] | None = None
) -> StyleClassification:
    """
    Maps what Creative Fingerprint already reported onto a rendering
    family. `scene_regions` contributes only weakly - region notes
    describe content, not medium.
    """
    text_parts: list[str] = []
    for key in ("visual_style", "graphic_style", "lighting_style"):
        value = (fingerprint or {}).get(key)
        if isinstance(value, str):
            text_parts.append(value)
    for region in scene_regions or []:
        note = region.get("notes")
        if isinstance(note, str):
            text_parts.append(note)

    haystack = " ".join(text_parts).lower()
    if not haystack.strip():
        # No evidence at all. Say so rather than defaulting to a mode -
        # the caller falls back to describing the style as analysed.
        return StyleClassification(SourceStyle.PHOTOGRAPHIC, 0.0, ["no style evidence available"])

    scores: dict[SourceStyle, float] = {}
    evidence: dict[SourceStyle, list[str]] = {}
    for style, signals in _SIGNALS.items():
        total = 0.0
        hits: list[str] = []
        for pattern, weight in signals:
            found = re.search(pattern, haystack)
            if found:
                total += weight
                hits.append(found.group(0))
        if total:
            scores[style] = total
            evidence[style] = hits

    if not scores:
        return StyleClassification(SourceStyle.PHOTOGRAPHIC, 0.0, ["no recognised style signals"])

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_style, top_score = ranked[0]
    runner_style, runner_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

    # Confidence: how dominant the winner is, capped at 1.0. A single
    # strong signal with nothing competing reads as confident; two
    # families neck-and-neck does not.
    total_all = sum(scores.values())
    confidence = min(top_score / total_all, 1.0) if total_all else 0.0

    # Genuine mixed media: two DIFFERENT families, both strong.
    if (
        runner_style is not None
        and FAMILY_OF[runner_style] is not FAMILY_OF[top_style]
        and runner_score >= top_score * _MIXED_THRESHOLD_RATIO
    ):
        return StyleClassification(
            SourceStyle.MIXED_MEDIA,
            round(confidence, 3),
            evidence[top_style] + evidence[runner_style],
            secondary=runner_style,
            scores={str(k): v for k, v in scores.items()},
        )

    return StyleClassification(
        top_style,
        round(confidence, 3),
        evidence[top_style],
        secondary=runner_style if runner_score else None,
        scores={str(k): v for k, v in scores.items()},
    )


# A slideshow is made as a SET: its slides are almost always in one
# medium. Incident e3fbf713 slide 2 is a hand-drawn illustration whose
# Creative Fingerprint described it as "Photographic with subtle digital
# enhancements" - a confident, wrong answer. Classified alone it drew the
# photographic criteria and its correctly-illustrated recreation was
# rejected for looking "more like a polished AI illustration than a real
# photograph", while its siblings passed as illustrations.
#
# Rather than adding a second opinion on the medium (the thing this
# module exists to avoid), the slideshow's own majority breaks the tie.
_CONSENSUS_MAJORITY = 0.6


def apply_slideshow_consensus(
    classification: StyleClassification, siblings: list[StyleClassification]
) -> StyleClassification:
    """
    When a slide's medium disagrees with a clear majority of its
    slideshow, treat it as MIXED rather than trusting either answer.

    Deliberately NOT a flip to the majority. Flipping would be a second
    guess dressed up as a rule, and a slideshow that genuinely mixes
    product photography with illustrated explainers would have its
    product shots forced into the wrong criteria. Downgrading to MIXED is
    the honest response to a real contradiction: the mixed criteria ask
    "is this well-made?" without penalising either medium, so a correct
    illustration is not failed for being illustrated and a correct
    photograph is not failed for being photographic.

    The evidence records both readings so the disagreement is visible
    rather than silently resolved.
    """
    others = [s for s in siblings if s is not classification and s.is_confident]
    if len(others) < 3:
        # Too few slides for a majority to mean anything.
        return classification

    counts: dict[RenderingFamily, int] = {}
    for sibling in others:
        counts[sibling.family] = counts.get(sibling.family, 0) + 1
    family, votes = max(counts.items(), key=lambda kv: kv[1])

    if family is classification.family or votes / len(others) < _CONSENSUS_MAJORITY:
        return classification

    return StyleClassification(
        SourceStyle.MIXED_MEDIA,
        round(votes / len(others), 3),
        [
            f"this slide reads as {classification.style}"
            f" ({', '.join(classification.evidence[:2])})",
            f"but {votes}/{len(others)} sibling slides read as {family}",
            "treating as mixed media rather than trusting either reading",
        ],
        secondary=classification.style,
        scores=classification.scores,
    )
