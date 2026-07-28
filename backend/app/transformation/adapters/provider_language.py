"""
Provider-facing language translation (adapter purity, enforcement family #1).

The adapter must never emit a raw internal enum, element id, or ownership/
requirement token into a provider request. Every internal value that needs to
appear in provider-facing text passes through an explicit translator here.

Design: explicit quality maps for the known vocabulary, plus a structural
safety net (element-id resolution + snake_case flattening) so a *new* internal
token can never leak silently even before its quality mapping is added. This is
the primary defence; the token scanner in the test suite is only the secondary
regression net.
"""
from __future__ import annotations
import re

# reserve-zone purpose enum -> provider-facing phrase
_PURPOSE = {
    "hook_caption": "a headline caption",
    "subhead": "secondary caption text",
    "price_card": "a price label",
    "cta": "a call-to-action button",
}

# known internal statement vocabulary -> phrase (quality layer; the flattener is the net)
_TERMS = {
    "promoted_product": "the promoted product",
    "product_withheld": "the product is kept hidden",
    "promoted_identity_withheld": "the product is visible but its offer is not revealed yet",
    "product_revealed": "the product is shown",
    "product_is_dominant_focus": "the product is the main focus",
    "price_is_evidence": "the price is shown as proof",
    "comparison_must_remain_legible": "the comparison stays easy to read",
    "two_subjects_equal_weight": "both subjects read as equally important",
    "product_native": "printed on the product",
    "creator_overlay": "an added caption",
}

_ELEMENT_ID = re.compile(r"\bs\d+_(?:t\d+|product|packaging)\b")
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def zone_purpose(purpose: str | None) -> str:
    return _PURPOSE.get(purpose or "", "text")


def element_phrase(ref: str, spec) -> str:
    """An element id (s1_product / s0_t3 / s2_packaging) -> a human phrase."""
    for p in getattr(spec, "products", ()):  # SpecProduct.ref == element_id
        if p.ref == ref:
            return "the product"
    if ref.endswith("_product"):
        return "the product"
    if ref.endswith("_packaging"):
        return "the on-pack text"
    return "the caption text"


def humanize(text: str, spec) -> str:
    """Translate any internal ids/enums embedded in free text to provider language."""
    if not text:
        return text
    out = _ELEMENT_ID.sub(lambda m: element_phrase(m.group(0), spec), text)
    for tok, phrase in _TERMS.items():
        out = re.sub(rf"(?<![a-z0-9_]){re.escape(tok)}(?![a-z0-9_])", phrase, out)
    # structural safety net: any remaining internal snake_case token -> spaced words
    out = _SNAKE.sub(lambda m: m.group(0).replace("_", " "), out)
    return out
