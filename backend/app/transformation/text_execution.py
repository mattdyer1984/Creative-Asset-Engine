"""
Text-execution seam (provider-independent).

Separates two decisions that were wrongly fused:
  - OWNERSHIP decides DISPOSITION (is this a separable creator overlay, or does it
    stay in the asset?) — from the frozen ownership decision.
  - FIDELITY (how accurately must the text survive?) is resolved from the smallest
    authoritative combination of: canonical trust status, Plan must-survive, and
    semantic role. Ownership class does NOT decide fidelity by itself.

Distinguishes: product label -> reference_fidelity; scene wording -> exact_text;
scene signage -> semantic_presence; infographic copy -> exact_text; branding ->
reference_fidelity; decorative -> none. When fidelity cannot be determined from
the available evidence, an explicit execution gap is emitted (never guessed).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from .ownership import OwnershipDecision

_BRAND_ROLES = {"logo_text", "logo", "brand"}


@dataclass(frozen=True)
class TextExecInput:
    ownership: Optional[OwnershipDecision]
    text: str
    text_status: Optional[str]        # canonical trust (exact_commercial_value | trusted_exact | meaning_preserve | None)
    must_survive: tuple               # Plan must-survive (identity | exact_text | meaning)
    semantic_role: Optional[str]      # OCR/Plan role where available (e.g. logo_text, price, headline)
    owning_product_ref: Optional[str] # product/reference target this text belongs to, if known


@dataclass(frozen=True)
class TextExecution:
    disposition: str                  # overlay_handoff | render_in_asset | unresolved
    fidelity: str                     # none | semantic_presence | exact_text | reference_fidelity | unresolved
    reference_target: Optional[str]   # for reference_fidelity: the owning product/reference
    source: str                       # provenance of the decision
    gap: str = ""


def resolve_text_execution(inp: TextExecInput) -> TextExecution:
    d = inp.ownership
    if d is None or d.ownership_class is None or d.is_uncertain:
        return TextExecution("unresolved", "unresolved", None, "ownership:uncertain",
                             gap="ownership uncertain — disposition not decidable; not guessed")

    # DISPOSITION from ownership only
    if d.proposed_handling == "eligible_for_separation":
        return TextExecution("overlay_handoff", "none", None, f"ownership:{d.ownership_class}@{d.confidence:.2f}")

    # FIDELITY from trust / role / must-survive (NOT ownership class)
    role = (inp.semantic_role or "").lower()
    ms = set(inp.must_survive or ())
    src = [f"disposition<-ownership:{d.ownership_class}"]

    if role in _BRAND_ROLES or "identity" in ms:
        src.append("fidelity<-role/identity(brand)")
        if inp.owning_product_ref:
            return TextExecution("render_in_asset", "reference_fidelity", inp.owning_product_ref, "+".join(src))
        return TextExecution("render_in_asset", "unresolved", None, "+".join(src),
                             gap="brand/label needs reference fidelity but owning reference target is unknown")
    if inp.text_status in ("exact_commercial_value", "trusted_exact") or "exact_text" in ms:
        src.append(f"fidelity<-trust:{inp.text_status}")
        return TextExecution("render_in_asset", "exact_text", None, "+".join(src))
    if inp.text_status == "meaning_preserve" or "meaning" in ms:
        src.append(f"fidelity<-trust:{inp.text_status}")
        return TextExecution("render_in_asset", "semantic_presence", None, "+".join(src))
    if not inp.text_status and role in ("", "other", "decorative"):
        src.append("fidelity<-decorative")
        return TextExecution("render_in_asset", "none", None, "+".join(src))
    return TextExecution("render_in_asset", "unresolved", None, "+".join(src),
                         gap="fidelity not determinable from trust/role/must-survive")
