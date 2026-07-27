"""
Coarse Attention Derivation.

This layer begins describing the DESTINATION (not the source). At this stage it
*derives* — it recovers, deterministically, the communication relationships and
attention structure already implicit in the Transformation Plan. It does not yet
*choose* between multiple valid destination strategies; when it later makes
creative choices not already encoded upstream, it becomes an Attention Planner.

It describes where a viewer's attention should go and what must be communicated,
provider-independently. A provider's composition is one valid solution.

The key abstraction is the CREATIVE CONTRACT:
  - the preserved communication relationships + focal constraints are the invariant;
  - everything not named in the contract is open design space.
Which of those open dimensions a given provider can actually vary is an ADAPTER
decision (provider capability), deliberately NOT enumerated here — that keeps
provider-independent planning separate from provider concerns.

Consumes ONLY the Transformation Plan + overlay brief. Never analysis/OCR.
Discipline (shared with Scene and Ownership): if a relationship cannot be
recovered confidently, emit an explicit gap — never invent it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from .plan import TransformationPlan, SlideDirective

_ZONE = {"hook_caption": "top", "price_card": "lower-corner", "subhead": "lower", "cta": "lower"}


@dataclass
class BriefItem:
    purpose: str                       # hook_caption | price_card | subhead | cta


@dataclass
class Focus:
    element_ref: str
    weight: str                        # primary | secondary | supporting | absent
    attention_role: str


@dataclass
class Relationship:
    relationship: str                  # a PERSUASION relationship, not a layout
    must_hold: bool
    rationale: str
    geometry: str = "provider's choice"


@dataclass
class AttentionOpening:
    purpose: str
    zone_intent: str                   # coarse intent, not coordinates
    strictness: str                    # high | medium


@dataclass
class CreativeContract:
    """The invariant. Everything NOT named here is open design space, resolved by
    the adapter against its own capabilities. We do not enumerate the free space."""
    invariants: list[str]              # preserved relationships + focal constraints
    reuse_source_framing: bool = False


@dataclass
class SlideAttention:
    slide_index: int
    role: str
    dynamics: str                      # calm | building | dramatic
    focal_order: list[Focus]
    communication_relationships: list[Relationship]
    attention_openings: list[AttentionOpening]
    creative_contract: CreativeContract
    gaps: list[str] = field(default_factory=list)


@dataclass
class AttentionDerivation:
    slideshow_id: str
    slides: list[SlideAttention]


def _dynamics(role: str, mechanisms: list[str]) -> str:
    if role == "hook":
        return "building"
    if role == "reveal":
        return "dramatic" if ("product_desirability" in mechanisms or "value" in mechanisms) else "building"
    if role in ("educational", "problem", "education_step"):
        return "calm"
    if role in ("comparison", "comparison_side"):
        return "building"
    return "calm"


def _relationships(slide: SlideDirective, mechanisms: list[str], has_price_brief: bool):
    rels, gaps = [], []
    role, subj = slide.role, slide.scene.subject_present
    if role == "hook":
        if not slide.promoted_product_allowed:
            rels.append(Relationship("product_withheld", True, "the hook withholds the product to open a curiosity gap"))
        if subj:
            rels.append(Relationship("reaction_drives_curiosity", True, "the person's reaction is the hook"))
    if role == "reveal" and slide.promoted_product_allowed:
        rels.append(Relationship("product_revealed", True, "the reveal presents the promoted product"))
        rels.append(Relationship("product_is_dominant_focus", True, "the product carries this slide"))
        gaps.append("whether the product must be shown *in use* (e.g. 'homemade') is not recoverable "
                    "from the Plan — coarse derivation cannot assert it")
    if role in ("educational", "problem", "education_step"):
        rels.append(Relationship("headline_explains_subject", True, "the headline explains the illustrated subject"))
    if role in ("comparison", "comparison_side"):
        rels.append(Relationship("comparison_must_remain_legible", True, "a comparison relationship carries the message"))
        gaps.append("comparison sub-type (before/after vs equally-weighted) not distinguishable from the Plan")
    if "value" in mechanisms and has_price_brief:
        rels.append(Relationship("price_is_evidence", True, "the discount/price is the persuasion proof, not decoration"))
    if "social_proof" in mechanisms or "scarcity" in mechanisms:
        rels.append(Relationship("quantity_or_proof_visible", True, "abundance/proof must read as evidence"))
    return rels, gaps


def _focal(slide: SlideDirective):
    focal = []
    prod = [e for e in slide.elements if e.kind == "product"]
    if slide.promoted_product_allowed and prod:
        focal.append(Focus(prod[0].element_id, "primary", "the product is the destination of attention"))
    if slide.scene.subject_present:
        w = "secondary" if (slide.promoted_product_allowed and prod) else "primary"
        focal.append(Focus("subject", w, "the person / reaction / illustrated figure"))
    focal.append(Focus("scene", "supporting", "environment and context"))
    if slide.role == "hook" and not slide.promoted_product_allowed:
        focal.append(Focus("promoted_product", "absent", "deliberately withheld on the hook"))
    return focal


def derive_attention(plan: TransformationPlan, brief: dict[int, list[BriefItem]]) -> AttentionDerivation:
    slides = []
    for s in plan.slides:
        items = brief.get(s.slide_index, [])
        has_price = any(b.purpose == "price_card" for b in items)
        rels, gaps = _relationships(s, plan.mechanisms_to_preserve, has_price)
        focal = _focal(s)
        openings = [AttentionOpening(b.purpose, _ZONE.get(b.purpose, "flexible"),
                                     "high" if b.purpose == "price_card" else "medium") for b in items]
        # The creative contract = the invariant only. The remaining design space is
        # implicit (everything else) and resolved by the adapter, not enumerated here.
        invariants = [r.relationship for r in rels] + \
                     [f"{f.element_ref} stays {f.weight}" for f in focal if f.weight in ("primary", "absent")]
        slides.append(SlideAttention(
            slide_index=s.slide_index, role=s.role, dynamics=_dynamics(s.role, plan.mechanisms_to_preserve),
            focal_order=focal, communication_relationships=rels, attention_openings=openings,
            creative_contract=CreativeContract(invariants=invariants), gaps=gaps,
        ))
    return AttentionDerivation(slideshow_id=plan.slideshow_id, slides=slides)
